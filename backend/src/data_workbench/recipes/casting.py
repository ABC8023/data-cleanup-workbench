from __future__ import annotations

from data_workbench.domain.recipe import CastNumberStep, ParseDateStep
from data_workbench.engine.sql import quote_identifier, quote_literal
from data_workbench.recipes.compiled import (
    CompiledOperation,
    error_count_query,
    replace_projection,
)

DECIMAL_DOT_KEEP_PATTERN = r"[^0-9.\-]"
DECIMAL_COMMA_KEEP_PATTERN = r"[^0-9,.\-]"


def _text(column: str) -> str:
    return f"CAST({quote_identifier(column)} AS VARCHAR)"


def _apply_on_error(
    step: ParseDateStep | CastNumberStep,
    converted: str,
    original: str,
) -> str:
    if step.on_error == "preserve":
        return f"COALESCE({converted}, {original})"
    return converted


def _failure_predicate(converted: str, original: str) -> str:
    return f"{original} IS NOT NULL AND {converted} IS NULL"


class ParseDateOperation:
    def _converted(self, step: ParseDateStep, text: str) -> str:
        attempts = ", ".join(f"try_strptime({text}, ?)" for _ in step.formats)
        return f"CAST(CAST(COALESCE({attempts}) AS DATE) AS VARCHAR)"

    def compile(self, step: ParseDateStep, input_sql: str) -> CompiledOperation:
        replacements: dict[str, str] = {}
        parameters: list[object] = []
        predicates: list[str] = []
        error_parameters: list[object] = []
        for column in step.columns:
            text = _text(column)
            converted = self._converted(step, text)
            replacements[column] = _apply_on_error(step, converted, text)
            parameters.extend(step.formats)
            if step.on_error == "quarantine":
                predicates.append(_failure_predicate(converted, text))
                error_parameters.extend(step.formats)
        error_query = (
            error_count_query(predicates, input_sql) if predicates else None
        )
        return CompiledOperation(
            sql=replace_projection(replacements, input_sql),
            parameters=parameters,
            error_query=error_query,
            error_parameters=error_parameters,
        )


class CastNumberOperation:
    def _cleaned(self, step: CastNumberStep, text: str) -> str:
        # Strip currency symbols and spaces but keep the decimal separator so
        # non-integral values fail integer casts instead of being mangled.
        if step.decimal_separator == ".":
            return (
                f"regexp_replace({text},"
                f" {quote_literal(DECIMAL_DOT_KEEP_PATTERN)}, '', 'g')"
            )
        stripped = (
            f"regexp_replace({text},"
            f" {quote_literal(DECIMAL_COMMA_KEEP_PATTERN)}, '', 'g')"
        )
        return f"replace(replace({stripped}, '.', ''), ',', '.')"

    def _converted(self, step: CastNumberStep, text: str) -> str:
        cleaned = f"nullif({self._cleaned(step, text)}, '')"
        double = f"TRY_CAST({cleaned} AS DOUBLE)"
        if step.target == "integer":
            # DuckDB rounds varchar decimals cast to BIGINT; require an
            # integral value so '12.5' fails instead of becoming 13.
            return (
                f"CAST(CASE WHEN {double} = trunc({double})"
                f" THEN CAST({double} AS BIGINT) END AS VARCHAR)"
            )
        return f"CAST({double} AS VARCHAR)"

    def compile(self, step: CastNumberStep, input_sql: str) -> CompiledOperation:
        replacements: dict[str, str] = {}
        predicates: list[str] = []
        for column in step.columns:
            text = _text(column)
            converted = self._converted(step, text)
            replacements[column] = _apply_on_error(step, converted, text)
            if step.on_error == "quarantine":
                predicates.append(_failure_predicate(converted, text))
        error_query = (
            error_count_query(predicates, input_sql) if predicates else None
        )
        return CompiledOperation(
            sql=replace_projection(replacements, input_sql),
            parameters=[],
            error_query=error_query,
            error_parameters=[],
        )
