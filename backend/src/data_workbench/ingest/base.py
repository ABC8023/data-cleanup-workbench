from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


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
