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
class CompiledQuery:
    sql: str
    parameters: list[object]


@dataclass(frozen=True)
class CompiledRecipe:
    sql: str
    parameters: list[object]
    error_queries: dict[str, CompiledQuery]


def compile_recipe(recipe: Recipe, input_sql: str) -> CompiledRecipe:
    sql = input_sql
    parameters: list[object] = []
    error_queries: dict[str, CompiledQuery] = {}
    for step in recipe.steps:
        compiled = compile_step(step, sql)
        if compiled.error_query is not None:
            # The error query embeds the step's input relation, so its text
            # binds the input's parameters first, then the predicate's.
            error_queries[step.id] = CompiledQuery(
                compiled.error_query,
                [*parameters, *compiled.error_parameters],
            )
        sql = compiled.sql
        # Operation placeholders precede the wrapped input in the SQL text.
        parameters = [*compiled.parameters, *parameters]
    return CompiledRecipe(sql=sql, parameters=parameters, error_queries=error_queries)
