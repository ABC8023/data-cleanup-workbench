from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from data_workbench.domain.profile import DatasetProfile
from data_workbench.engine.duckdb_runtime import DuckDBRuntime
from data_workbench.ingest.base import TableHandle
from data_workbench.ingest.registry import AdapterRegistry
from data_workbench.profiling.profiler import Profiler


@pytest.fixture
def connection(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    return DuckDBRuntime("512MB", 1).connect(tmp_path / "session")


@pytest.fixture
def table_handle(tmp_path: Path) -> TableHandle:
    source = tmp_path / "customers.csv"
    source.write_text(
        "customer_id,amount\nc1,10\nc2,20\nc3,30\n,40\n",
        encoding="utf-8",
    )
    return AdapterRegistry().inspect(source, tmp_path / "session")[0]


def test_profile_reports_schema_nulls_uniqueness_and_samples(
    connection: duckdb.DuckDBPyConnection,
    table_handle: TableHandle,
) -> None:
    profile = Profiler(sample_rows=50).profile(
        connection, table_handle, "fixture-sha256", lambda: None
    )

    assert profile.source_fingerprint == "fixture-sha256"
    assert profile.table == "data"
    assert profile.row_count == 4
    assert not profile.sampled
    by_name = {column.name: column for column in profile.columns}
    assert by_name["customer_id"].null_count == 1
    assert by_name["customer_id"].distinct_count == 3
    assert len(by_name["customer_id"].examples) <= 10


def test_profile_reports_types_extremes_and_top_values(
    connection: duckdb.DuckDBPyConnection,
    table_handle: TableHandle,
) -> None:
    profile = Profiler(sample_rows=50).profile(
        connection, table_handle, "fixture-sha256", lambda: None
    )

    by_name = {column.name: column for column in profile.columns}
    assert by_name["amount"].inferred_type == "VARCHAR"
    assert by_name["amount"].min_value == "10"
    assert by_name["amount"].max_value == "40"
    assert by_name["customer_id"].examples == ["c1", "c2", "c3"]
    assert by_name["customer_id"].top_values == [("c1", 1), ("c2", 1), ("c3", 1)]


def test_profile_calls_cancel_check_between_columns(
    connection: duckdb.DuckDBPyConnection,
    table_handle: TableHandle,
) -> None:
    calls: list[int] = []

    def cancel_check() -> None:
        calls.append(len(calls))
        if len(calls) > 1:
            raise TimeoutError("cancelled")

    with pytest.raises(TimeoutError, match="cancelled"):
        Profiler(sample_rows=50).profile(connection, table_handle, "sha", cancel_check)
    assert len(calls) == 2


def test_repeated_profiles_are_identical(
    connection: duckdb.DuckDBPyConnection,
    table_handle: TableHandle,
) -> None:
    profiler = Profiler(sample_rows=50)

    first = profiler.profile(connection, table_handle, "fixture-sha256", lambda: None)
    second = profiler.profile(connection, table_handle, "fixture-sha256", lambda: None)

    assert first.model_dump() == second.model_dump()
    assert DatasetProfile.model_validate(first.model_dump()) == first


def test_profile_marks_sampled_when_rows_exceed_sample_budget(
    connection: duckdb.DuckDBPyConnection,
    table_handle: TableHandle,
) -> None:
    profile = Profiler(sample_rows=2).profile(connection, table_handle, "sha", lambda: None)

    assert profile.sampled
    by_name = {column.name: column for column in profile.columns}
    assert by_name["customer_id"].null_count == 1
    assert len(by_name["customer_id"].examples) <= 2 + 1


def test_profile_quotes_hostile_column_names(tmp_path: Path) -> None:
    connection = DuckDBRuntime("512MB", 1).connect(tmp_path / "session")
    connection.execute('CREATE TABLE hostile ("weird""name" VARCHAR)')
    connection.execute("INSERT INTO hostile VALUES ('a'), (NULL)")
    handle = TableHandle("data", "SELECT * FROM hostile", "test:memory")

    profile = Profiler(sample_rows=50).profile(connection, handle, "sha", lambda: None)

    assert profile.columns[0].name == 'weird"name'
    assert profile.columns[0].null_count == 1
    assert profile.columns[0].examples == ["a"]
