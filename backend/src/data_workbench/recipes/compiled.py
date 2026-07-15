from __future__ import annotations

from dataclasses import dataclass

from data_workbench.engine.sql import quote_identifier


@dataclass(frozen=True)
class CompiledOperation:
    """One compiled step.

    ``parameters`` bind placeholders the operation added; they always precede
    the input relation's own parameters in the final SQL text. ``error_query``
    (with ``error_parameters`` appended after the input's parameters) counts
    input rows the step could not convert, for quarantine handling.
    """

    sql: str
    parameters: list[object]
    error_query: str | None
    error_parameters: list[object]


def replace_projection(replacements: dict[str, str], input_sql: str) -> str:
    clauses = ", ".join(
        f"{expression} AS {quote_identifier(column)}"
        for column, expression in replacements.items()
    )
    return f"SELECT * REPLACE ({clauses}) FROM ({input_sql})"


def error_count_query(predicates: list[str], input_sql: str) -> str:
    combined = " OR ".join(f"({predicate})" for predicate in predicates)
    return f"SELECT count(*) FROM ({input_sql}) WHERE {combined}"
