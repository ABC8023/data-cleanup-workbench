from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Protocol

import duckdb
from pydantic import BaseModel, ConfigDict, Field

from data_workbench.domain.recipe import ExactDeduplicateStep, Recipe
from data_workbench.engine.sql import quote_identifier, quote_literal
from data_workbench.ingest.base import SYSTEM_COLUMNS, TableHandle
from data_workbench.recipes.registry import compile_chain

ROW_ID_COLUMN = "__workbench_row_id"
PREVIEW_SAMPLE_ROWS = 100
AFFECTED_SAMPLE_ROWS = 50
ROW_REMOVING_OPERATIONS = frozenset(
    {"exact_deduplicate", "apply_duplicate_decision"}
)

OutputFormat = Literal["csv", "parquet"]


class ExecutionError(ValueError):
    """Raised when execution cannot produce a validated, reconciled output."""


class CancelContext(Protocol):
    def raise_if_cancelled(self) -> None: ...


class PreviewResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    before_rows: list[dict[str, object]]
    after_rows: list[dict[str, object]]
    schema_before: dict[str, str]
    schema_after: dict[str, str]
    null_deltas: dict[str, int]
    row_count_delta: int
    validation_failures: list[str]


class ExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    cleaned_path: Path
    quarantine_path: Path | None
    input_rows: int = Field(ge=0)
    output_rows: int = Field(ge=0)
    removed_rows: int = Field(ge=0)
    quarantined_rows: int = Field(ge=0)


def _count(connection: duckdb.DuckDBPyConnection, sql: str) -> int:
    counted = connection.sql(f"SELECT count(*) FROM ({sql})").fetchone()
    return int(counted[0]) if counted is not None else 0


def _column_names(connection: duckdb.DuckDBPyConnection, sql: str) -> list[str]:
    described = connection.sql(f"DESCRIBE SELECT * FROM ({sql})").fetchall()
    return [str(row[0]) for row in described]


class RecipeExecutor:
    def __init__(self, preview_rows: int = PREVIEW_SAMPLE_ROWS) -> None:
        self.preview_rows = preview_rows

    def _visible(
        self, connection: duckdb.DuckDBPyConnection, scan_sql: str
    ) -> str:
        hidden = [
            name
            for name in _column_names(connection, scan_sql)
            if name in SYSTEM_COLUMNS
        ]
        if not hidden:
            return scan_sql
        excluded = ", ".join(quote_identifier(name) for name in hidden)
        return f"SELECT * EXCLUDE ({excluded}) FROM ({scan_sql})"

    def _rows(
        self, connection: duckdb.DuckDBPyConnection, sql: str
    ) -> list[dict[str, object]]:
        relation = connection.sql(sql)
        columns = list(relation.columns)
        return [dict(zip(columns, row)) for row in relation.fetchall()]

    def _schema(
        self, connection: duckdb.DuckDBPyConnection, sql: str
    ) -> dict[str, str]:
        described = connection.sql(f"DESCRIBE SELECT * FROM ({sql})").fetchall()
        return {str(row[0]): str(row[1]) for row in described}

    def preview(
        self,
        connection: duckdb.DuckDBPyConnection,
        handle: TableHandle,
        recipe: Recipe,
        affected_predicates: tuple[str, ...] = (),
    ) -> PreviewResult:
        base = self._visible(connection, handle.scan_sql)
        parts = [f"(SELECT * FROM ({base}) LIMIT {self.preview_rows})"]
        parts.extend(
            f"(SELECT * FROM ({base}) WHERE {predicate}"
            f" LIMIT {AFFECTED_SAMPLE_ROWS})"
            for predicate in affected_predicates
        )
        sample_sql = " UNION ".join(parts)
        before_rows = self._rows(connection, sample_sql)
        schema_before = self._schema(connection, sample_sql)
        try:
            plan = compile_chain(recipe, sample_sql, exclude_failures=True)
            after_sql = plan[-1].output_sql if plan else sample_sql
            after_rows = self._rows(connection, after_sql)
            schema_after = self._schema(connection, after_sql)
        except duckdb.Error as error:
            return PreviewResult(
                before_rows=before_rows,
                after_rows=[],
                schema_before=schema_before,
                schema_after={},
                null_deltas={},
                row_count_delta=0,
                validation_failures=[f"recipe failed to compile: {error}"],
            )
        validation_failures = [
            f"step '{compiled.step_id}': {count} sampled row(s) cannot be"
            " converted and would be quarantined"
            for compiled in plan
            if compiled.failure_predicate is not None
            and (
                count := _count(
                    connection,
                    f"SELECT * FROM ({compiled.input_sql})"
                    f" WHERE {compiled.failure_predicate}",
                )
            )
        ]
        shared = [name for name in schema_after if name in schema_before]
        null_deltas = {
            name: sum(1 for row in after_rows if row.get(name) is None)
            - sum(1 for row in before_rows if row.get(name) is None)
            for name in shared
        }
        return PreviewResult(
            before_rows=before_rows,
            after_rows=after_rows,
            schema_before=schema_before,
            schema_after=schema_after,
            null_deltas=null_deltas,
            row_count_delta=len(after_rows) - len(before_rows),
            validation_failures=validation_failures,
        )

    def _copy(
        self,
        connection: duckdb.DuckDBPyConnection,
        sql: str,
        destination: Path,
        output_format: OutputFormat,
    ) -> None:
        options = (
            "FORMAT PARQUET" if output_format == "parquet" else "FORMAT CSV, HEADER"
        )
        connection.execute(
            f"COPY ({sql}) TO {quote_literal(destination)} ({options})"
        )

    def _read_back(self, destination: Path, output_format: OutputFormat) -> str:
        if output_format == "parquet":
            return f"SELECT * FROM read_parquet({quote_literal(destination)})"
        return (
            "SELECT * FROM read_csv("
            f"{quote_literal(destination)}, all_varchar=true, header=true)"
        )

    def _fsync(self, destination: Path) -> None:
        with destination.open("ab") as stream:
            stream.flush()
            os.fsync(stream.fileno())

    def _resolve_full_row_dedup(
        self,
        connection: duckdb.DuckDBPyConnection,
        recipe: Recipe,
        chain_input: str,
    ) -> Recipe:
        # Row-id threading breaks SELECT DISTINCT *; pin full-row dedup to the
        # explicit user columns instead.
        steps = list(recipe.steps)
        for index, step in enumerate(steps):
            if isinstance(step, ExactDeduplicateStep) and not step.columns:
                columns = [
                    name
                    for name in _column_names(connection, chain_input)
                    if name != ROW_ID_COLUMN
                ]
                steps[index] = step.model_copy(update={"columns": columns})
        return recipe.model_copy(update={"steps": steps})

    def execute(
        self,
        connection: duckdb.DuckDBPyConnection,
        handle: TableHandle,
        recipe: Recipe,
        destination_dir: Path,
        output_format: OutputFormat,
        context: CancelContext,
    ) -> ExecutionResult:
        destination_dir.mkdir(parents=True, exist_ok=True)
        extension = "parquet" if output_format == "parquet" else "csv"
        cleaned_partial = destination_dir / f"cleaned.partial.{extension}"
        quarantine_partial = destination_dir / f"quarantine.partial.{extension}"
        cleaned_final = destination_dir / f"cleaned.{extension}"
        quarantine_final = destination_dir / f"quarantine.{extension}"
        base = self._visible(connection, handle.scan_sql)
        needs_quarantine = any(
            step.on_error == "quarantine" for step in recipe.steps
        )
        temp_table = "__workbench_execution_base"
        row_id = quote_identifier(ROW_ID_COLUMN)
        try:
            input_rows = _count(connection, base)
            if needs_quarantine:
                # Materialize row ids once so quarantine capture and the
                # cleaned output agree on row identity across queries.
                connection.execute(
                    f"CREATE OR REPLACE TEMP TABLE {temp_table} AS"
                    f" SELECT *, row_number() OVER () AS {row_id} FROM ({base})"
                )
                chain_input = f"SELECT * FROM {temp_table}"
                recipe = self._resolve_full_row_dedup(
                    connection, recipe, chain_input
                )
            else:
                chain_input = base
            plan = compile_chain(recipe, chain_input, exclude_failures=True)
            final_sql = plan[-1].output_sql if plan else chain_input
            context.raise_if_cancelled()
            if needs_quarantine:
                cleaned_sql = f"SELECT * EXCLUDE ({row_id}) FROM ({final_sql})"
                id_selects = " UNION ".join(
                    f"SELECT {row_id} AS rid FROM ({compiled.input_sql})"
                    f" WHERE {compiled.failure_predicate}"
                    for compiled in plan
                    if compiled.failure_predicate is not None
                )
                quarantine_sql = (
                    f"SELECT * EXCLUDE ({row_id}) FROM {temp_table}"
                    f" WHERE {row_id} IN (SELECT rid FROM ({id_selects}))"
                )
            else:
                cleaned_sql = final_sql
                quarantine_sql = None
            self._copy(connection, cleaned_sql, cleaned_partial, output_format)
            context.raise_if_cancelled()
            quarantined_rows = 0
            if quarantine_sql is not None:
                self._copy(
                    connection, quarantine_sql, quarantine_partial, output_format
                )
                quarantined_rows = _count(
                    connection, self._read_back(quarantine_partial, output_format)
                )
            output_rows = _count(
                connection, self._read_back(cleaned_partial, output_format)
            )
            removed_rows = input_rows - output_rows - quarantined_rows
            removes_rows = any(
                step.operation in ROW_REMOVING_OPERATIONS
                for step in recipe.steps
            )
            if removed_rows < 0 or (removed_rows > 0 and not removes_rows):
                raise ExecutionError(
                    "output rows do not reconcile with input rows"
                )
            self._fsync(cleaned_partial)
            os.replace(cleaned_partial, cleaned_final)
            quarantine_path: Path | None = None
            if quarantine_sql is not None and quarantined_rows > 0:
                self._fsync(quarantine_partial)
                os.replace(quarantine_partial, quarantine_final)
                quarantine_path = quarantine_final
            else:
                quarantine_partial.unlink(missing_ok=True)
            return ExecutionResult(
                cleaned_path=cleaned_final,
                quarantine_path=quarantine_path,
                input_rows=input_rows,
                output_rows=output_rows,
                removed_rows=removed_rows,
                quarantined_rows=quarantined_rows,
            )
        except duckdb.Error as error:
            raise ExecutionError(f"execution failed: {error}") from error
        finally:
            cleaned_partial.unlink(missing_ok=True)
            quarantine_partial.unlink(missing_ok=True)
            if needs_quarantine:
                connection.execute(f"DROP TABLE IF EXISTS {temp_table}")
