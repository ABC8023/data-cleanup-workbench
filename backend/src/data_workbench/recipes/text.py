from __future__ import annotations

from data_workbench.domain.recipe import NormalizeTextStep, ReplaceValueStep
from data_workbench.engine.sql import quote_identifier
from data_workbench.recipes.compiled import (
    CompiledOperation,
    literal,
    replace_projection,
)


def _text(column: str) -> str:
    return f"CAST({quote_identifier(column)} AS VARCHAR)"


class NormalizeTextOperation:
    def compile(self, step: NormalizeTextStep, input_sql: str) -> CompiledOperation:
        replacements: dict[str, str] = {}
        for column in step.columns:
            expression = _text(column)
            if step.trim:
                expression = f"trim({expression})"
            if step.case != "preserve":
                expression = f"{step.case}({expression})"
            replacements[column] = expression
        return CompiledOperation(sql=replace_projection(replacements, input_sql))


class ReplaceValueOperation:
    def compile(self, step: ReplaceValueStep, input_sql: str) -> CompiledOperation:
        replacements: dict[str, str] = {}
        for column in step.columns:
            text = _text(column)
            replacements[column] = (
                f"CASE WHEN {text} IS NOT DISTINCT FROM {literal(step.old)}"
                f" THEN {literal(step.new)} ELSE {text} END"
            )
        return CompiledOperation(sql=replace_projection(replacements, input_sql))
