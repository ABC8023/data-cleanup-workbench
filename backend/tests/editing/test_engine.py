from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from data_workbench.editing.engine import (
    EditEngine,
    InvalidEdit,
    UnknownColumn,
    load_edits,
    resolve_handle,
)
from data_workbench.editing.parser import parse_command
from data_workbench.engine.duckdb_runtime import DuckDBRuntime
from data_workbench.ingest.base import TableHandle
from data_workbench.ingest.registry import AdapterRegistry

CSV_BYTES = b"customer_id,name,city\nc1, Ada ,kul\nc2,lin,\nc3,N/A,jhb\n"


@pytest.fixture
def session_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "session"
    directory.mkdir()
    return directory


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "customers.csv"
    path.write_bytes(CSV_BYTES)
    return path


@pytest.fixture
def handle(source: Path, session_dir: Path) -> TableHandle:
    return AdapterRegistry().inspect(source, session_dir)[0]


@pytest.fixture
def connection(session_dir: Path) -> duckdb.DuckDBPyConnection:
    return DuckDBRuntime("512MB", 1).connect(session_dir)


def test_preview_replace_reports_affected_rows_and_samples(
    connection: duckdb.DuckDBPyConnection,
    handle: TableHandle,
) -> None:
    command = parse_command("replace 'N/A' with null in column name")

    preview = EditEngine().preview(connection, handle, command)

    assert preview.table == "data"
    assert preview.columns_before == ["customer_id", "name", "city"]
    assert preview.columns_after == ["customer_id", "name", "city"]
    assert preview.affected_row_count == 1
    assert [(sample.before, sample.after) for sample in preview.samples] == [
        ("N/A", None)
    ]


def test_preview_rename_reports_schema_change_without_data_change(
    connection: duckdb.DuckDBPyConnection,
    handle: TableHandle,
) -> None:
    command = parse_command("rename column customer_id to customer")

    preview = EditEngine().preview(connection, handle, command)

    assert preview.columns_after == ["customer", "name", "city"]
    assert preview.affected_row_count == 0
    assert [(sample.before, sample.after) for sample in preview.samples] == [
        ("c1", "c1"),
        ("c2", "c2"),
        ("c3", "c3"),
    ]


def test_preview_drop_shows_values_that_disappear(
    connection: duckdb.DuckDBPyConnection,
    handle: TableHandle,
) -> None:
    preview = EditEngine().preview(connection, handle, parse_command("drop column city"))

    assert preview.columns_after == ["customer_id", "name"]
    assert all(sample.after is None for sample in preview.samples)


def test_apply_materializes_new_handle_and_keeps_source_immutable(
    connection: duckdb.DuckDBPyConnection,
    handle: TableHandle,
    source: Path,
    session_dir: Path,
) -> None:
    command = parse_command("replace 'N/A' with null in column name")

    applied = EditEngine().apply(connection, session_dir, handle, command)

    assert source.read_bytes() == CSV_BYTES
    assert applied.sequence == 1
    assert applied.row_count == 3
    assert (session_dir / applied.staged_filename).exists()
    assert not (session_dir / f"{applied.staged_filename}.partial").exists()
    edited = resolve_handle(session_dir, handle)
    assert edited.scan_sql != handle.scan_sql
    names = [row[0] for row in connection.sql(
        f"SELECT name FROM ({edited.scan_sql}) ORDER BY customer_id"
    ).fetchall()]
    assert names == [" Ada ", "lin", None]


def test_apply_chains_edits_in_order(
    connection: duckdb.DuckDBPyConnection,
    handle: TableHandle,
    session_dir: Path,
) -> None:
    engine = EditEngine()

    first = engine.apply(
        connection, session_dir, handle, parse_command("trim column name")
    )
    second = engine.apply(
        connection,
        session_dir,
        resolve_handle(session_dir, handle),
        parse_command("uppercase column name"),
    )

    assert (first.sequence, second.sequence) == (1, 2)
    assert [edit.sequence for edit in load_edits(session_dir)] == [1, 2]
    final = resolve_handle(session_dir, handle)
    names = [row[0] for row in connection.sql(
        f"SELECT name FROM ({final.scan_sql}) ORDER BY customer_id"
    ).fetchall()]
    assert names == ["ADA", "LIN", "N/A"]


def test_unknown_column_and_invalid_edits_raise_typed_errors(
    connection: duckdb.DuckDBPyConnection,
    handle: TableHandle,
    session_dir: Path,
) -> None:
    engine = EditEngine()

    with pytest.raises(UnknownColumn, match="missing"):
        engine.preview(connection, handle, parse_command("drop column missing"))
    with pytest.raises(InvalidEdit, match="already exists"):
        engine.preview(
            connection, handle, parse_command("rename column name to city")
        )

    single = tmp_single_column(connection)
    with pytest.raises(InvalidEdit, match="only column"):
        engine.preview(connection, single, parse_command("drop column value"))
    assert load_edits(session_dir) == []


def tmp_single_column(connection: duckdb.DuckDBPyConnection) -> TableHandle:
    connection.execute("CREATE TABLE single_column (value VARCHAR)")
    connection.execute("INSERT INTO single_column VALUES ('a')")
    return TableHandle("data", "SELECT * FROM single_column", "test:memory")


def test_fill_nulls_counts_null_rows(
    connection: duckdb.DuckDBPyConnection,
    handle: TableHandle,
) -> None:
    command = parse_command("fill nulls in column city with 'unknown'")

    preview = EditEngine().preview(connection, handle, command)

    assert preview.affected_row_count == 1
    assert [(sample.before, sample.after) for sample in preview.samples] == [
        (None, "unknown")
    ]
