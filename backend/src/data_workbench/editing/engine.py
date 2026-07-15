from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import duckdb

from data_workbench.domain.edit import (
    AppliedEdit,
    DropColumnCommand,
    EditCommand,
    EditPreview,
    EditSample,
    RenameColumnCommand,
    ReplaceValueCommand,
    SetCaseCommand,
    TrimWhitespaceCommand,
)
from data_workbench.engine.sql import quote_identifier, quote_literal
from data_workbench.ingest.base import SYSTEM_COLUMNS, TableHandle

PREVIEW_ROWS = 20
EDIT_LOG_FILENAME = "edits.json"


class UnknownColumn(ValueError):
    """Raised when an edit references a column that does not exist."""


class InvalidEdit(ValueError):
    """Raised when an edit is well-formed but cannot be applied safely."""


@dataclass(frozen=True)
class _CompiledEdit:
    select_exprs: list[str]
    columns_after: list[str]
    changed_predicate: str | None
    after_expr: str | None


def _text(column: str) -> str:
    return f"CAST({quote_identifier(column)} AS VARCHAR)"


def _literal(value: str | None) -> str:
    if value is None:
        return "CAST(NULL AS VARCHAR)"
    return quote_literal(value)


def _compile(command: EditCommand, columns: list[str]) -> _CompiledEdit:
    if command.column not in columns:
        raise UnknownColumn(f"column {command.column!r} does not exist")
    quoted = quote_identifier(command.column)
    if isinstance(command, RenameColumnCommand):
        if not command.new_name.strip():
            raise InvalidEdit("new column name must not be blank")
        if command.new_name in columns:
            raise InvalidEdit(f"column {command.new_name!r} already exists")
        exprs = [
            f"{quote_identifier(name)} AS {quote_identifier(command.new_name)}"
            if name == command.column
            else quote_identifier(name)
            for name in columns
        ]
        renamed = [
            command.new_name if name == command.column else name for name in columns
        ]
        return _CompiledEdit(exprs, renamed, None, None)
    if isinstance(command, DropColumnCommand):
        if len(columns) == 1:
            raise InvalidEdit("cannot drop the only column")
        kept = [name for name in columns if name != command.column]
        return _CompiledEdit([quote_identifier(name) for name in kept], kept, None, None)
    if isinstance(command, ReplaceValueCommand):
        old = _literal(command.old)
        after = (
            f"CASE WHEN {_text(command.column)} IS NOT DISTINCT FROM {old}"
            f" THEN {_literal(command.new)} ELSE {_text(command.column)} END"
        )
        predicate = f"{_text(command.column)} IS NOT DISTINCT FROM {old}"
    elif isinstance(command, SetCaseCommand):
        function = "upper" if command.case == "upper" else "lower"
        after = f"{function}({_text(command.column)})"
        predicate = (
            f"{quoted} IS NOT NULL AND {_text(command.column)} <> {after}"
        )
    elif isinstance(command, TrimWhitespaceCommand):
        after = f"trim({_text(command.column)})"
        predicate = (
            f"{quoted} IS NOT NULL AND {_text(command.column)} <> {after}"
        )
    else:  # pragma: no cover - exhaustive over the discriminated union
        raise InvalidEdit(f"unsupported operation {command!r}")
    exprs = [
        f"{after} AS {quote_identifier(name)}"
        if name == command.column
        else quote_identifier(name)
        for name in columns
    ]
    return _CompiledEdit(exprs, list(columns), predicate, after)


def load_edits(session_dir: Path) -> list[AppliedEdit]:
    path = session_dir / EDIT_LOG_FILENAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    return [AppliedEdit.model_validate(item) for item in raw]


def _save_edits(session_dir: Path, edits: list[AppliedEdit]) -> None:
    path = session_dir / EDIT_LOG_FILENAME
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(
            json.dumps([edit.model_dump(mode="json") for edit in edits], indent=2)
        )
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def resolve_handle(session_dir: Path, base: TableHandle) -> TableHandle:
    applied = [edit for edit in load_edits(session_dir) if edit.table == base.name]
    if not applied:
        return base
    last = applied[-1]
    staged = session_dir / last.staged_filename
    return TableHandle(
        base.name,
        f"SELECT * FROM read_parquet({quote_literal(staged)})",
        f"edit:{base.name}:{last.sequence}",
    )


class EditEngine:
    def __init__(self, preview_rows: int = PREVIEW_ROWS) -> None:
        self.preview_rows = preview_rows

    def _columns(
        self, connection: duckdb.DuckDBPyConnection, handle: TableHandle
    ) -> list[str]:
        described = connection.sql(
            f"DESCRIBE SELECT * FROM ({handle.scan_sql})"
        ).fetchall()
        return [str(row[0]) for row in described if str(row[0]) not in SYSTEM_COLUMNS]

    def preview(
        self,
        connection: duckdb.DuckDBPyConnection,
        handle: TableHandle,
        command: EditCommand,
    ) -> EditPreview:
        columns = self._columns(connection, handle)
        compiled = _compile(command, columns)
        if compiled.changed_predicate is None:
            affected = 0
            samples = self._structural_samples(connection, handle, command)
        else:
            counted = connection.sql(
                f"SELECT count(*) FROM ({handle.scan_sql})"
                f" WHERE {compiled.changed_predicate}"
            ).fetchone()
            affected = int(counted[0]) if counted is not None else 0
            samples = [
                EditSample(
                    before=None if row[0] is None else str(row[0]),
                    after=None if row[1] is None else str(row[1]),
                )
                for row in connection.sql(
                    f"SELECT {_text(command.column)} AS before,"
                    f" {compiled.after_expr} AS after"
                    f" FROM ({handle.scan_sql})"
                    f" WHERE {compiled.changed_predicate}"
                    f" ORDER BY before NULLS FIRST"
                    f" LIMIT {self.preview_rows}"
                ).fetchall()
            ]
        return EditPreview(
            command=command,
            table=handle.name,
            columns_before=columns,
            columns_after=compiled.columns_after,
            affected_row_count=affected,
            samples=samples,
        )

    def _structural_samples(
        self,
        connection: duckdb.DuckDBPyConnection,
        handle: TableHandle,
        command: EditCommand,
    ) -> list[EditSample]:
        values = [
            None if row[0] is None else str(row[0])
            for row in connection.sql(
                f"SELECT {_text(command.column)} AS value"
                f" FROM ({handle.scan_sql})"
                f" WHERE {quote_identifier(command.column)} IS NOT NULL"
                f" ORDER BY value"
                f" LIMIT {self.preview_rows}"
            ).fetchall()
        ]
        dropped = isinstance(command, DropColumnCommand)
        return [
            EditSample(before=value, after=None if dropped else value)
            for value in values
        ]

    def apply(
        self,
        connection: duckdb.DuckDBPyConnection,
        session_dir: Path,
        handle: TableHandle,
        command: EditCommand,
    ) -> AppliedEdit:
        columns = self._columns(connection, handle)
        compiled = _compile(command, columns)
        edits = load_edits(session_dir)
        sequence = len(edits) + 1
        staged_filename = f"edit-{sequence:04d}.parquet"
        destination = session_dir / staged_filename
        partial = session_dir / f"{staged_filename}.partial"
        select_sql = (
            f"SELECT {', '.join(compiled.select_exprs)} FROM ({handle.scan_sql})"
        )
        try:
            connection.execute(
                f"COPY ({select_sql}) TO {quote_literal(partial)} (FORMAT PARQUET)"
            )
            with partial.open("ab") as stream:
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(partial, destination)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        counted = connection.sql(
            f"SELECT count(*) FROM read_parquet({quote_literal(destination)})"
        ).fetchone()
        applied = AppliedEdit(
            sequence=sequence,
            table=handle.name,
            command=command,
            staged_filename=staged_filename,
            row_count=int(counted[0]) if counted is not None else 0,
        )
        _save_edits(session_dir, [*edits, applied])
        return applied
