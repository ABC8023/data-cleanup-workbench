from __future__ import annotations

from data_workbench.domain.recipe import (
    ApplyDuplicateDecisionStep,
    DropColumnStep,
    ExactDeduplicateStep,
    RenameColumnStep,
)
from data_workbench.engine.sql import quote_identifier
from data_workbench.recipes.compiled import CompiledOperation

ROW_ID_COLUMN = "__workbench_row_id"


class UnsupportedDecisionContext(ValueError):
    """Raised when a duplicate decision cannot compile without group context."""


def _no_error(sql: str) -> CompiledOperation:
    return CompiledOperation(sql=sql)


class DropColumnOperation:
    def compile(self, step: DropColumnStep, input_sql: str) -> CompiledOperation:
        excluded = ", ".join(quote_identifier(name) for name in step.columns)
        return _no_error(f"SELECT * EXCLUDE ({excluded}) FROM ({input_sql})")


class RenameColumnOperation:
    def compile(self, step: RenameColumnStep, input_sql: str) -> CompiledOperation:
        old = quote_identifier(step.columns[0])
        new = quote_identifier(step.new_name)
        return _no_error(f"SELECT * RENAME ({old} AS {new}) FROM ({input_sql})")


class ExactDeduplicateOperation:
    def compile(self, step: ExactDeduplicateStep, input_sql: str) -> CompiledOperation:
        if not step.columns:
            return _no_error(f"SELECT DISTINCT * FROM ({input_sql})")
        row_id = quote_identifier(ROW_ID_COLUMN)
        partition = ", ".join(quote_identifier(name) for name in step.columns)
        direction = "ASC" if step.keep == "first" else "DESC"
        return _no_error(
            f"SELECT * EXCLUDE ({row_id}) FROM ("
            f"SELECT *, row_number() OVER () AS {row_id} FROM ({input_sql})"
            f") QUALIFY row_number() OVER ("
            f"PARTITION BY {partition} ORDER BY {row_id} {direction}) = 1"
        )


class DuplicateDecisionOperation:
    def compile(
        self, step: ApplyDuplicateDecisionStep, input_sql: str
    ) -> CompiledOperation:
        if step.action == "keep_separate":
            return _no_error(f"SELECT * FROM ({input_sql})")
        raise UnsupportedDecisionContext(
            "remove_record and merge_fields compile only during execution with"
            " a reviewed duplicate group (delivered with the duplicate engine)"
        )
