from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

HASH_CHUNK_BYTES = 1024 * 1024
MAX_BATCH_ROWS = 10_000
MAX_BATCH_CELLS = 50_000
MAX_BATCH_UTF8_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class TableHandle:
    name: str
    scan_sql: str
    source_locator: str


class Adapter(Protocol):
    def inspect(self, source: Path, session_dir: Path) -> list[TableHandle]: ...


class UnsupportedFormat(ValueError):
    """Raised when no safe adapter exists for an input format."""


class MalformedInput(ValueError):
    """Raised when input bytes do not form the declared format."""


def fingerprint_source(source: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        while chunk := stream.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return base64.urlsafe_b64encode(digest.digest()).decode("ascii").rstrip("=")


def estimate_utf8_bytes(row: Mapping[str, str | None]) -> int:
    return sum(len(value.encode("utf-8")) for value in row.values() if value is not None)


def batch_would_exceed_limits(
    *,
    batch_rows: int,
    batch_cells: int,
    batch_utf8_bytes: int,
    row_cells: int,
    row_utf8_bytes: int,
) -> bool:
    if batch_rows == 0:
        return False
    return (
        batch_rows + 1 > MAX_BATCH_ROWS
        or batch_cells + row_cells > MAX_BATCH_CELLS
        or batch_utf8_bytes + row_utf8_bytes > MAX_BATCH_UTF8_BYTES
    )
