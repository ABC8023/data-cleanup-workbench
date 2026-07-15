from __future__ import annotations

from dataclasses import dataclass

from data_workbench.engine.sql import quote_identifier, quote_literal


@dataclass(frozen=True)
class CompiledOperation:
    """One compiled step.

    ``sql`` selects the transformed relation over the step's input. String
    values are inlined through the centralized ``quote_literal`` helper so the
    compiled text can run inside ``COPY`` statements, which cannot bind
    parameters. ``failure_predicate`` (set only for quarantine steps) is a SQL
    boolean over the step's INPUT relation matching rows the step cannot
    convert.
    """

    sql: str
    failure_predicate: str | None = None


def literal(value: str | None) -> str:
    if value is None:
        return "CAST(NULL AS VARCHAR)"
    return quote_literal(value)


def replace_projection(replacements: dict[str, str], input_sql: str) -> str:
    clauses = ", ".join(
        f"{expression} AS {quote_identifier(column)}"
        for column, expression in replacements.items()
    )
    return f"SELECT * REPLACE ({clauses}) FROM ({input_sql})"


def combined_predicate(predicates: list[str]) -> str:
    return " OR ".join(f"({predicate})" for predicate in predicates)
