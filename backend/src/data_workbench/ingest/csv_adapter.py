from __future__ import annotations

from pathlib import Path

from data_workbench.engine.sql import quote_literal
from data_workbench.ingest.base import MalformedInput, TableHandle

SNIFF_BYTES = 64 * 1024


def _validate_text_sample(source: Path) -> None:
    try:
        with source.open("rb") as stream:
            sample = stream.read(SNIFF_BYTES)
        sample.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise MalformedInput(f"CSV is not valid UTF-8 text: {exc}") from exc
    if not sample:
        raise MalformedInput("CSV is empty")
    if b"\x00" in sample:
        raise MalformedInput("CSV contains binary data")


class CsvAdapter:
    def inspect(self, source: Path, session_dir: Path) -> list[TableHandle]:
        del session_dir
        _validate_text_sample(source)
        scan = f"read_csv({quote_literal(source)}, all_varchar=true, filename=true)"
        return [TableHandle("data", f"SELECT * FROM {scan}", "csv:line")]
