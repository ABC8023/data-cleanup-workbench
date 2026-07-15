from __future__ import annotations

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from data_workbench.domain.profile import DatasetProfile
from data_workbench.ingest.base import TableHandle
from data_workbench.profiling.profiler import Profiler


def profile_values(values: list[int | None]) -> DatasetProfile:
    connection = duckdb.connect()
    try:
        connection.execute("CREATE TABLE source_values (value BIGINT)")
        for value in values:
            connection.execute("INSERT INTO source_values VALUES (?)", [value])
        handle = TableHandle("data", "SELECT value FROM source_values", "test:memory")
        return Profiler(sample_rows=50).profile(connection, handle, "property-sha", lambda: None)
    finally:
        connection.close()


@settings(max_examples=30, deadline=None)
@given(st.lists(st.one_of(st.none(), st.integers(min_value=-(2**62), max_value=2**62)), max_size=50))
def test_profile_invariants(values: list[int | None]) -> None:
    profile = profile_values(values)

    assert profile.row_count == len(values)
    column = profile.columns[0]
    assert column.null_count == values.count(None)
    assert 0 <= column.null_count <= profile.row_count
    assert 0 <= column.distinct_count <= profile.row_count - column.null_count
    assert len(column.examples) <= 10
    assert column.examples == sorted(column.examples)
    assert len(column.top_values) <= 10
    assert sum(count for _, count in column.top_values) <= profile.row_count - column.null_count
    assert profile_values(values).model_dump() == profile.model_dump()
