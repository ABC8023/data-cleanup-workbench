from __future__ import annotations

import asyncio
from pathlib import Path

import duckdb
import pytest

from data_workbench.domain.recipe import (
    CastNumberStep,
    ExactDeduplicateStep,
    NormalizeTextStep,
    Recipe,
    RenameColumnStep,
    ReplaceValueStep,
)
from data_workbench.engine.duckdb_runtime import DuckDBRuntime
from data_workbench.ingest.base import TableHandle
from data_workbench.ingest.registry import AdapterRegistry
from data_workbench.recipes.executor import ExecutionError, RecipeExecutor

SOURCE = "c" * 43
CSV_BYTES = (
    b"customer_id,amount\n"
    b"c1,RM 1200\n"
    b"c2,x\n"
    b"c3,10\n"
    b"c1,RM 1200\n"
)


class StubContext:
    def raise_if_cancelled(self) -> None:
        return None


class CancelledContext:
    def raise_if_cancelled(self) -> None:
        raise asyncio.CancelledError


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


def recipe(*steps: object) -> Recipe:
    return Recipe(source_fingerprint=SOURCE, steps=list(steps))  # type: ignore[arg-type]


def test_preview_reports_null_deltas_and_schema(
    connection: duckdb.DuckDBPyConnection, handle: TableHandle
) -> None:
    preview = RecipeExecutor().preview(
        connection,
        handle,
        recipe(
            ReplaceValueStep(
                id="r", columns=["amount"], old="x", new=None, on_error="preserve"
            ),
            RenameColumnStep(
                id="n", columns=["customer_id"], new_name="customer",
                on_error="preserve",
            ),
        ),
    )

    assert len(preview.before_rows) == 4
    assert len(preview.after_rows) == 4
    assert "filename" not in preview.schema_before
    assert list(preview.schema_before) == ["customer_id", "amount"]
    assert list(preview.schema_after) == ["customer", "amount"]
    assert preview.null_deltas == {"amount": 1}
    assert preview.row_count_delta == 0
    assert preview.validation_failures == []


def test_preview_reports_quarantine_and_compile_failures(
    connection: duckdb.DuckDBPyConnection, handle: TableHandle
) -> None:
    quarantined = RecipeExecutor().preview(
        connection,
        handle,
        recipe(
            CastNumberStep(
                id="c", columns=["amount"], target="integer",
                on_error="quarantine",
            )
        ),
    )
    broken = RecipeExecutor().preview(
        connection,
        handle,
        recipe(
            NormalizeTextStep(id="n", columns=["missing"], on_error="preserve")
        ),
    )

    assert quarantined.row_count_delta == -1
    assert any("quarantined" in note for note in quarantined.validation_failures)
    assert broken.after_rows == []
    assert any("failed to compile" in note for note in broken.validation_failures)


def test_execute_promotes_validated_outputs_and_keeps_source(
    connection: duckdb.DuckDBPyConnection,
    handle: TableHandle,
    source: Path,
    session_dir: Path,
) -> None:
    outputs = session_dir / "outputs"

    result = RecipeExecutor().execute(
        connection,
        handle,
        recipe(
            CastNumberStep(
                id="c", columns=["amount"], target="integer", on_error="preserve"
            )
        ),
        outputs,
        "parquet",
        StubContext(),
    )

    assert source.read_bytes() == CSV_BYTES
    assert result.cleaned_path == outputs / "cleaned.parquet"
    assert result.quarantine_path is None
    assert (result.input_rows, result.output_rows) == (4, 4)
    assert (result.removed_rows, result.quarantined_rows) == (0, 0)
    assert not list(outputs.glob("*.partial.*"))
    amounts = connection.sql(
        f"SELECT amount FROM read_parquet('{result.cleaned_path.as_posix()}')"
        " ORDER BY amount"
    ).fetchall()
    assert [row[0] for row in amounts] == ["10", "1200", "1200", "x"]


def test_execute_quarantines_unconvertible_rows(
    connection: duckdb.DuckDBPyConnection,
    handle: TableHandle,
    session_dir: Path,
) -> None:
    outputs = session_dir / "outputs"

    result = RecipeExecutor().execute(
        connection,
        handle,
        recipe(
            CastNumberStep(
                id="c", columns=["amount"], target="integer",
                on_error="quarantine",
            )
        ),
        outputs,
        "parquet",
        StubContext(),
    )

    assert (result.input_rows, result.output_rows) == (4, 3)
    assert (result.removed_rows, result.quarantined_rows) == (0, 1)
    assert result.quarantine_path == outputs / "quarantine.parquet"
    quarantined = connection.sql(
        "SELECT customer_id, amount FROM"
        f" read_parquet('{result.quarantine_path.as_posix()}')"
    ).fetchall()
    assert quarantined == [("c2", "x")]


def test_execute_counts_deduplicated_rows_as_removed(
    connection: duckdb.DuckDBPyConnection,
    handle: TableHandle,
    session_dir: Path,
) -> None:
    result = RecipeExecutor().execute(
        connection,
        handle,
        recipe(
            ExactDeduplicateStep(
                id="d", columns=["customer_id"], keep="first",
                on_error="preserve",
            )
        ),
        session_dir / "outputs",
        "csv",
        StubContext(),
    )

    assert result.cleaned_path.suffix == ".csv"
    assert (result.input_rows, result.output_rows) == (4, 3)
    assert result.removed_rows == 1


def test_failed_execution_removes_partials_and_keeps_source(
    connection: duckdb.DuckDBPyConnection,
    handle: TableHandle,
    source: Path,
    session_dir: Path,
) -> None:
    outputs = session_dir / "outputs"

    with pytest.raises(ExecutionError, match="execution failed"):
        RecipeExecutor().execute(
            connection,
            handle,
            recipe(
                NormalizeTextStep(id="n", columns=["missing"], on_error="preserve")
            ),
            outputs,
            "parquet",
            StubContext(),
        )

    assert source.read_bytes() == CSV_BYTES
    assert list(outputs.iterdir()) == []


def test_cancelled_execution_leaves_no_outputs(
    connection: duckdb.DuckDBPyConnection,
    handle: TableHandle,
    session_dir: Path,
) -> None:
    outputs = session_dir / "outputs"

    with pytest.raises(asyncio.CancelledError):
        RecipeExecutor().execute(
            connection,
            handle,
            recipe(
                NormalizeTextStep(id="n", columns=["amount"], on_error="preserve")
            ),
            outputs,
            "parquet",
            CancelledContext(),
        )

    assert list(outputs.iterdir()) == []
