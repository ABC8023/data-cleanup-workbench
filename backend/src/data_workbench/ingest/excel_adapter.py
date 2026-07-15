from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

import openpyxl  # type: ignore[import-untyped]
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from data_workbench.engine.sql import quote_literal
from data_workbench.ingest.base import (
    MAX_BATCH_CELLS,
    MAX_BATCH_ROWS,
    MAX_BATCH_UTF8_BYTES,
    MalformedInput,
    TableHandle,
    batch_would_exceed_limits,
    estimate_utf8_bytes,
    fingerprint_source,
)


def _filename_component(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:8] or "sheet"


def _is_empty_row(row: Sequence[Any]) -> bool:
    return all(value is None or (isinstance(value, str) and not value.strip()) for value in row)


def _split_header(
    rows: Iterable[Sequence[Any]],
) -> tuple[Sequence[Any] | None, Iterator[Sequence[Any]]]:
    iterator = iter(rows)
    for row in iterator:
        if not _is_empty_row(row):
            return row, iterator
    return None, iterator


def _validate_headers(header: Sequence[Any]) -> list[str]:
    names = ["" if value is None else str(value).strip() for value in header]
    if any(not name for name in names):
        raise MalformedInput("Excel headers must not be blank")
    normalized = [name.casefold() for name in names]
    if len(set(normalized)) != len(normalized):
        raise MalformedInput("Excel headers must be unique after normalization")
    return names


def _stringify_excel(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _write_string_parquet(
    staged: Path,
    names: list[str],
    rows: Iterable[Sequence[Any]],
) -> None:
    schema = pa.schema([(name, pa.string()) for name in names])
    batch: list[dict[str, str | None]] = []
    batch_cells = 0
    batch_utf8_bytes = 0
    with pq.ParquetWriter(staged, schema) as writer:
        for row in rows:
            if _is_empty_row(row):
                continue
            string_row = {
                name: _stringify_excel(row[index] if index < len(row) else None)
                for index, name in enumerate(names)
            }
            row_cells = len(names)
            row_utf8_bytes = estimate_utf8_bytes(string_row)
            if batch_would_exceed_limits(
                batch_rows=len(batch),
                batch_cells=batch_cells,
                batch_utf8_bytes=batch_utf8_bytes,
                row_cells=row_cells,
                row_utf8_bytes=row_utf8_bytes,
            ):
                writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                batch = []
                batch_cells = 0
                batch_utf8_bytes = 0
            batch.append(string_row)
            batch_cells += row_cells
            batch_utf8_bytes += row_utf8_bytes
            if (
                len(batch) >= MAX_BATCH_ROWS
                or batch_cells >= MAX_BATCH_CELLS
                or batch_utf8_bytes >= MAX_BATCH_UTF8_BYTES
            ):
                writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                batch = []
                batch_cells = 0
                batch_utf8_bytes = 0
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=schema))


class ExcelAdapter:
    def inspect(self, source: Path, session_dir: Path) -> list[TableHandle]:
        session_dir.mkdir(parents=True, exist_ok=True)
        try:
            workbook = openpyxl.load_workbook(
                source,
                read_only=True,
                data_only=True,
                keep_links=False,
            )
        except (OSError, ValueError, openpyxl.utils.exceptions.InvalidFileException) as exc:
            raise MalformedInput(f"invalid Excel workbook: {exc}") from exc

        handles: list[TableHandle] = []
        try:
            source_fingerprint = fingerprint_source(source)
            normalized_sheet_names = [
                sheet.title.strip().casefold() for sheet in workbook.worksheets
            ]
            if len(set(normalized_sheet_names)) != len(normalized_sheet_names):
                raise MalformedInput(
                    "Excel sheet names must be unique after normalization"
                )
            for index, sheet in enumerate(workbook.worksheets):
                header, rows = _split_header(sheet.iter_rows(values_only=True))
                if header is None:
                    continue
                names = _validate_headers(header)
                staged = session_dir / (
                    f"xlsx-{source_fingerprint}-sheet-{index:04d}-"
                    f"{_filename_component(sheet.title)}.parquet"
                )
                _write_string_parquet(staged, names, rows)
                scan = f"SELECT * FROM read_parquet({quote_literal(staged)})"
                handles.append(
                    TableHandle(sheet.title, scan, f"xlsx:{sheet.title}:row")
                )
        except MalformedInput:
            raise
        except (OSError, ValueError, pa.ArrowException) as exc:
            raise MalformedInput(f"could not stage Excel workbook: {exc}") from exc
        finally:
            workbook.close()

        if not handles:
            raise MalformedInput("workbook contains no non-empty sheets")
        return handles
