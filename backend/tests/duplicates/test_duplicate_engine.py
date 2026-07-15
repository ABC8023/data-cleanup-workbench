from __future__ import annotations

import duckdb
import pytest

from data_workbench.domain.duplicates import DuplicateConfig
from data_workbench.duplicates.engine import DuplicateEngine, InvalidDuplicateConfig
from data_workbench.ingest.base import TableHandle

CONFIG = DuplicateConfig(
    blocking_columns=["city"],
    comparison_weights={"name": 0.7, "email": 0.3},
    threshold=0.9,
)

ROWS = [
    ("kul", "John Smith", "j@x.com"),
    ("KUL", "JOHN SMITH", "j@x.com"),
    ("kul", "Alice Wong", "a@x.com"),
    ("jhb", "John Smith", "j@x.com"),
    ("kul", "John  Smith", "j@x.com"),
]


@pytest.fixture
def fixture() -> tuple[duckdb.DuckDBPyConnection, TableHandle]:
    connection = duckdb.connect()
    connection.execute(
        "CREATE TABLE people (city VARCHAR, name VARCHAR, email VARCHAR)"
    )
    for row in ROWS:
        connection.execute("INSERT INTO people VALUES (?, ?, ?)", list(row))
    return connection, TableHandle("data", "SELECT * FROM people", "test:people")


def test_fuzzy_matching_blocks_before_scoring(
    fixture: tuple[duckdb.DuckDBPyConnection, TableHandle],
) -> None:
    connection, handle = fixture

    groups = DuplicateEngine().find_fuzzy(connection, handle, CONFIG, 100)

    assert len(groups) == 1
    group = groups[0]
    # Rows 1, 2, and 5 share the normalized "kul" block and score together;
    # row 4 has an identical name but a different block, so it is never
    # compared. Row 3 scores below the threshold.
    assert group.row_ids == ["1", "2", "5"]
    # Display values join the comparison fields in sorted order (email, name).
    assert {"j@x.com | John Smith", "j@x.com | JOHN SMITH"} <= set(
        group.display_values
    )
    assert group.confidence <= 1
    assert group.evidence["name"] == 1.0
    assert all(
        candidate.evidence and candidate.confidence <= 1
        for candidate in group.candidates
    )


def test_candidates_never_carry_decisions(
    fixture: tuple[duckdb.DuckDBPyConnection, TableHandle],
) -> None:
    connection, handle = fixture

    groups = DuplicateEngine().find_fuzzy(connection, handle, CONFIG, 100)

    assert groups
    assert all(group.decision is None for group in groups)


def test_repeated_searches_are_deterministic(
    fixture: tuple[duckdb.DuckDBPyConnection, TableHandle],
) -> None:
    connection, handle = fixture
    engine = DuplicateEngine()

    first = engine.find_fuzzy(connection, handle, CONFIG, 100)
    second = engine.find_fuzzy(connection, handle, CONFIG, 100)

    assert [group.model_dump() for group in first] == [
        group.model_dump() for group in second
    ]


def test_invalid_configurations_raise_typed_errors(
    fixture: tuple[duckdb.DuckDBPyConnection, TableHandle],
) -> None:
    connection, handle = fixture
    engine = DuplicateEngine()

    with pytest.raises(InvalidDuplicateConfig, match="required"):
        engine.find_fuzzy(
            connection,
            handle,
            DuplicateConfig(
                blocking_columns=[], comparison_weights={"name": 1}, threshold=0.9
            ),
            100,
        )
    with pytest.raises(InvalidDuplicateConfig, match="unknown columns"):
        engine.find_fuzzy(
            connection,
            handle,
            DuplicateConfig(
                blocking_columns=["missing"],
                comparison_weights={"name": 1},
                threshold=0.9,
            ),
            100,
        )


def test_block_and_candidate_caps_bound_the_search(
    fixture: tuple[duckdb.DuckDBPyConnection, TableHandle],
) -> None:
    connection, handle = fixture

    capped_block = DuplicateEngine(max_block_rows=2).find_fuzzy(
        connection, handle, CONFIG, 100
    )
    capped_candidates = DuplicateEngine().find_fuzzy(connection, handle, CONFIG, 1)

    # The kul block has 4 members, above the block cap, so it is skipped.
    assert capped_block == []
    assert sum(len(group.candidates) for group in capped_candidates) <= 1


def test_find_exact_groups_identical_rows(
    fixture: tuple[duckdb.DuckDBPyConnection, TableHandle],
) -> None:
    connection, handle = fixture
    connection.execute(
        "INSERT INTO people VALUES ('kul', 'John Smith', 'j@x.com')"
    )

    groups = DuplicateEngine().find_exact(
        connection, handle, ["city", "name", "email"]
    )

    assert len(groups) == 1
    assert groups[0].row_ids == ["1", "6"]
    assert all(
        candidate.confidence == 1.0 for candidate in groups[0].candidates
    )
    assert groups[0].decision is None
    with pytest.raises(InvalidDuplicateConfig, match="columns"):
        DuplicateEngine().find_exact(connection, handle, [])
