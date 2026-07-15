from __future__ import annotations

from typing import Callable

import duckdb
import pytest

from data_workbench.domain.recipe import (
    ApplyDuplicateDecisionStep,
    BaseStep,
    CastNumberStep,
    DropColumnStep,
    ExactDeduplicateStep,
    NormalizeTextStep,
    ParseDateStep,
    Recipe,
    RenameColumnStep,
    ReplaceValueStep,
)
from data_workbench.engine.sql import quote_identifier
from data_workbench.recipes.registry import compile_recipe, compile_step
from data_workbench.recipes.rows import UnsupportedDecisionContext

SOURCE = "b" * 43

OperationRunner = Callable[[BaseStep, list[str | None]], list[str | None]]


@pytest.fixture
def operation_runner() -> OperationRunner:
    def run(step: BaseStep, values: list[str | None]) -> list[str | None]:
        connection = duckdb.connect()
        column = quote_identifier(step.columns[0])
        connection.execute(
            f"CREATE TABLE source_rows (rid INTEGER, {column} VARCHAR)"
        )
        for index, value in enumerate(values):
            connection.execute(
                "INSERT INTO source_rows VALUES (?, ?)", [index, value]
            )
        compiled = compile_step(step, "SELECT * FROM source_rows")
        rows = connection.execute(
            f"SELECT {column} FROM ({compiled.sql}) ORDER BY rid"
        ).fetchall()
        return [row[0] for row in rows]

    return run


def test_normalize_text_is_idempotent(operation_runner: OperationRunner) -> None:
    step = NormalizeTextStep(
        id="n", columns=["currency"], trim=True, case="upper", on_error="preserve"
    )

    once = operation_runner(step, [" usd ", "EUR", None])
    twice = operation_runner(step, once)

    assert twice == once == ["USD", "EUR", None]


def test_parse_date_handles_preserve_and_set_null(
    operation_runner: OperationRunner,
) -> None:
    values = ["03/04/2026", "2026-01-02", "nonsense", None]
    formats = ["%Y-%m-%d", "%d/%m/%Y"]

    preserved = operation_runner(
        ParseDateStep(
            id="d", columns=["seen"], formats=formats, on_error="preserve"
        ),
        values,
    )
    nulled = operation_runner(
        ParseDateStep(
            id="d", columns=["seen"], formats=formats, on_error="set_null"
        ),
        values,
    )

    assert preserved == ["2026-04-03", "2026-01-02", "nonsense", None]
    assert nulled == ["2026-04-03", "2026-01-02", None, None]


def test_cast_number_normalizes_symbols_and_separators(
    operation_runner: OperationRunner,
) -> None:
    integers = operation_runner(
        CastNumberStep(
            id="c", columns=["amount"], target="integer", on_error="preserve"
        ),
        ["RM 1,200", "7", "12.5", "x", None],
    )
    decimals = operation_runner(
        CastNumberStep(
            id="c", columns=["amount"], target="decimal", on_error="set_null"
        ),
        ["RM 1,200.50", "10", "x", None],
    )
    european = operation_runner(
        CastNumberStep(
            id="c",
            columns=["amount"],
            target="decimal",
            decimal_separator=",",
            on_error="set_null",
        ),
        ["1.200,50", "7,5"],
    )

    assert integers == ["1200", "7", "12.5", "x", None]
    assert decimals == ["1200.5", "10.0", None, None]
    assert european == ["1200.5", "7.5"]


def test_replace_value_swaps_exact_values_and_nulls(
    operation_runner: OperationRunner,
) -> None:
    to_null = operation_runner(
        ReplaceValueStep(
            id="r", columns=["name"], old="N/A", new=None, on_error="preserve"
        ),
        ["N/A", "ok", None],
    )
    fill = operation_runner(
        ReplaceValueStep(
            id="r", columns=["name"], old=None, new="unknown", on_error="preserve"
        ),
        ["N/A", None],
    )

    assert to_null == [None, "ok", None]
    assert fill == ["N/A", "unknown"]


def test_quarantine_error_query_counts_failures() -> None:
    connection = duckdb.connect()
    connection.execute("CREATE TABLE source_rows (amount VARCHAR)")
    connection.execute(
        "INSERT INTO source_rows VALUES ('10'), ('x'), (''), (NULL)"
    )
    step = CastNumberStep(
        id="c", columns=["amount"], target="integer", on_error="quarantine"
    )

    compiled = compile_step(step, "SELECT * FROM source_rows")

    assert compiled.failure_predicate is not None
    counted = connection.execute(
        "SELECT count(*) FROM (SELECT * FROM source_rows)"
        f" WHERE {compiled.failure_predicate}"
    ).fetchone()
    assert counted is not None and counted[0] == 2


def _multi_column_connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    connection.execute(
        "CREATE TABLE source_rows (rid INTEGER, k VARCHAR, v VARCHAR)"
    )
    for rid, key, value in [(0, "a", "1"), (1, "a", "2"), (2, "b", "3")]:
        connection.execute("INSERT INTO source_rows VALUES (?, ?, ?)", [rid, key, value])
    return connection


def test_drop_and_rename_reshape_schema() -> None:
    connection = _multi_column_connection()

    dropped = compile_step(
        DropColumnStep(id="d", columns=["v"], on_error="preserve"),
        "SELECT * FROM source_rows",
    )
    renamed = compile_step(
        RenameColumnStep(
            id="r", columns=["k"], new_name="key", on_error="preserve"
        ),
        "SELECT * FROM source_rows",
    )

    assert connection.sql(dropped.sql).columns == ["rid", "k"]
    assert connection.sql(renamed.sql).columns == ["rid", "key", "v"]


def test_exact_deduplicate_keeps_first_or_last() -> None:
    connection = _multi_column_connection()

    def rows(keep: str) -> list[tuple[str, str]]:
        compiled = compile_step(
            ExactDeduplicateStep(
                id="x", columns=["k"], keep=keep, on_error="preserve"
            ),
            "SELECT * FROM source_rows",
        )
        return [
            (row[1], row[2])
            for row in connection.execute(
                f"SELECT * FROM ({compiled.sql}) ORDER BY rid"
            ).fetchall()
        ]

    assert rows("first") == [("a", "1"), ("b", "3")]
    assert rows("last") == [("a", "2"), ("b", "3")]


def test_full_row_deduplicate_uses_distinct() -> None:
    connection = duckdb.connect()
    connection.execute("CREATE TABLE source_rows (k VARCHAR)")
    connection.execute("INSERT INTO source_rows VALUES ('a'), ('a'), ('b')")

    compiled = compile_step(
        ExactDeduplicateStep(id="x", columns=[], keep="first", on_error="preserve"),
        "SELECT * FROM source_rows",
    )

    values = sorted(
        row[0] for row in connection.execute(compiled.sql).fetchall()
    )
    assert values == ["a", "b"]


def test_duplicate_decisions_require_review_context() -> None:
    keep = compile_step(
        ApplyDuplicateDecisionStep(
            id="k",
            columns=[],
            on_error="preserve",
            group_id="g1",
            action="keep_separate",
        ),
        "SELECT 1 AS x",
    )
    assert "SELECT * FROM" in keep.sql

    with pytest.raises(UnsupportedDecisionContext, match="reviewed duplicate group"):
        compile_step(
            ApplyDuplicateDecisionStep(
                id="m",
                columns=[],
                on_error="preserve",
                group_id="g1",
                action="remove_record",
                survivor_row_id="r1",
            ),
            "SELECT 1 AS x",
        )


def test_compile_recipe_chains_steps_and_orders_parameters() -> None:
    connection = duckdb.connect()
    connection.execute("CREATE TABLE source_rows (rid INTEGER, name VARCHAR)")
    for rid, value in enumerate(["n/a", " ada ", None]):
        connection.execute("INSERT INTO source_rows VALUES (?, ?)", [rid, value])
    recipe = Recipe(
        source_fingerprint=SOURCE,
        steps=[
            NormalizeTextStep(
                id="n", columns=["name"], trim=True, case="upper", on_error="preserve"
            ),
            ReplaceValueStep(
                id="r", columns=["name"], old="N/A", new=None, on_error="preserve"
            ),
        ],
    )

    compiled_sql = compile_recipe(recipe, "SELECT * FROM source_rows")
    rows = connection.execute(
        f"SELECT name FROM ({compiled_sql}) ORDER BY rid"
    ).fetchall()

    assert [row[0] for row in rows] == [None, "ADA", None]
    assert "IS NOT DISTINCT FROM 'N/A'" in compiled_sql
