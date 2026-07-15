from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from data_workbench.domain.recipe import Recipe, RecipeStep
from data_workbench.recipes.casting import CastNumberOperation, ParseDateOperation
from data_workbench.recipes.compiled import CompiledOperation
from data_workbench.recipes.rows import (
    DropColumnOperation,
    DuplicateDecisionOperation,
    ExactDeduplicateOperation,
    RenameColumnOperation,
)
from data_workbench.recipes.text import NormalizeTextOperation, ReplaceValueOperation


class UnknownOperation(ValueError):
    """Raised when a recipe step has no registered compiler."""


class Operation(Protocol):
    # Each compiler narrows to its own step model; dispatch guarantees the match.
    def compile(self, step: Any, input_sql: str) -> CompiledOperation: ...


OPERATIONS: dict[str, Operation] = {
    "rename_column": RenameColumnOperation(),
    "normalize_text": NormalizeTextOperation(),
    "parse_date": ParseDateOperation(),
    "cast_number": CastNumberOperation(),
    "replace_value": ReplaceValueOperation(),
    "drop_column": DropColumnOperation(),
    "exact_deduplicate": ExactDeduplicateOperation(),
    "apply_duplicate_decision": DuplicateDecisionOperation(),
}


def compile_step(step: RecipeStep, input_sql: str) -> CompiledOperation:
    operation = OPERATIONS.get(step.operation)
    if operation is None:
        raise UnknownOperation(step.operation)
    return operation.compile(step, input_sql)


@dataclass(frozen=True)
class CompiledStep:
    step_id: str
    operation: str
    input_sql: str
    output_sql: str
    failure_predicate: str | None


def compile_chain(
    recipe: Recipe,
    input_sql: str,
    *,
    exclude_failures: bool,
) -> list[CompiledStep]:
    """Fold ordered steps into nested SELECTs.

    With ``exclude_failures`` (preview and execution), rows a quarantine step
    cannot convert are filtered out of that step's input so they disappear
    from the cleaned output; callers capture them separately via
    ``failure_predicate`` over ``input_sql``.
    """
    plan: list[CompiledStep] = []
    sql = input_sql
    for step in recipe.steps:
        compiled = compile_step(step, sql)
        output_sql = compiled.sql
        if compiled.failure_predicate is not None and exclude_failures:
            filtered = (
                f"SELECT * FROM ({sql})"
                f" WHERE NOT coalesce({compiled.failure_predicate}, false)"
            )
            output_sql = compile_step(step, filtered).sql
        plan.append(
            CompiledStep(
                step_id=step.id,
                operation=step.operation,
                input_sql=sql,
                output_sql=output_sql,
                failure_predicate=compiled.failure_predicate,
            )
        )
        sql = output_sql
    return plan


def compile_recipe(recipe: Recipe, input_sql: str) -> str:
    plan = compile_chain(recipe, input_sql, exclude_failures=True)
    return plan[-1].output_sql if plan else f"SELECT * FROM ({input_sql})"
