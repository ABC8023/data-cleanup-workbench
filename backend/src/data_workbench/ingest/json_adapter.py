from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, BinaryIO

import ijson  # type: ignore[import-untyped]
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

MAX_COLUMNS = 10_000


def _iter_json_objects(source: Path, ndjson: bool) -> Iterator[dict[str, Any]]:
    try:
        with source.open("rb") as stream:
            records: Iterable[Any]
            if ndjson:
                records = _iter_ndjson(stream)
            else:
                records = ijson.items(stream, "item", use_float=True)
            for record in records:
                if not isinstance(record, dict):
                    raise MalformedInput("JSON records must be objects")
                yield record
    except MalformedInput:
        raise
    except (OSError, UnicodeError, ValueError, ijson.JSONError) as exc:
        raise MalformedInput(f"invalid JSON input: {exc}") from exc


def _iter_ndjson(stream: BinaryIO) -> Iterator[Any]:
    for line_number, line in enumerate(stream, start=1):
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise MalformedInput(f"invalid NDJSON record at line {line_number}") from exc


def _flatten(
    value: dict[str, Any],
    prefix: str = "",
    flattened: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if flattened is None:
        flattened = {}
    for raw_key, nested_value in value.items():
        key = f"{prefix}.{raw_key}" if prefix else str(raw_key)
        if isinstance(nested_value, dict):
            _flatten(nested_value, key, flattened)
        else:
            if key in flattened:
                raise MalformedInput(f"JSON keys collide after flattening: {key}")
            flattened[key] = nested_value
    return flattened


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class JsonAdapter:
    def __init__(self, ndjson: bool) -> None:
        self.ndjson = ndjson

    def inspect(self, source: Path, session_dir: Path) -> list[TableHandle]:
        keys: set[str] = set()
        for record in _iter_json_objects(source, self.ndjson):
            keys.update(_flatten(record))
            if len(keys) > MAX_COLUMNS:
                raise MalformedInput(f"JSON contains more than {MAX_COLUMNS} columns")

        sorted_keys = sorted(keys)
        if not sorted_keys:
            raise MalformedInput("JSON contains no object fields")

        session_dir.mkdir(parents=True, exist_ok=True)
        staged = session_dir / f"json-{fingerprint_source(source)}.parquet"
        schema = pa.schema([(key, pa.string()) for key in sorted_keys])
        try:
            with pq.ParquetWriter(staged, schema) as writer:
                rows: list[dict[str, str | None]] = []
                batch_cells = 0
                batch_utf8_bytes = 0
                for record in _iter_json_objects(source, self.ndjson):
                    flattened = _flatten(record)
                    row = {key: _stringify(flattened.get(key)) for key in sorted_keys}
                    row_cells = len(sorted_keys)
                    row_utf8_bytes = estimate_utf8_bytes(row)
                    if batch_would_exceed_limits(
                        batch_rows=len(rows),
                        batch_cells=batch_cells,
                        batch_utf8_bytes=batch_utf8_bytes,
                        row_cells=row_cells,
                        row_utf8_bytes=row_utf8_bytes,
                    ):
                        writer.write_table(pa.Table.from_pylist(rows, schema=schema))
                        rows = []
                        batch_cells = 0
                        batch_utf8_bytes = 0
                    rows.append(row)
                    batch_cells += row_cells
                    batch_utf8_bytes += row_utf8_bytes
                    if (
                        len(rows) >= MAX_BATCH_ROWS
                        or batch_cells >= MAX_BATCH_CELLS
                        or batch_utf8_bytes >= MAX_BATCH_UTF8_BYTES
                    ):
                        writer.write_table(pa.Table.from_pylist(rows, schema=schema))
                        rows = []
                        batch_cells = 0
                        batch_utf8_bytes = 0
                if rows:
                    writer.write_table(pa.Table.from_pylist(rows, schema=schema))
        except (OSError, pa.ArrowException) as exc:
            raise MalformedInput(f"could not stage JSON input: {exc}") from exc

        scan = f"SELECT * FROM read_parquet({quote_literal(staged)})"
        return [TableHandle("data", scan, "json:record")]
