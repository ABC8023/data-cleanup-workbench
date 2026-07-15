from __future__ import annotations

import codecs
from pathlib import Path

from data_workbench.engine.sql import quote_literal
from data_workbench.ingest.base import MalformedInput, TableHandle

VALIDATION_CHUNK_BYTES = 64 * 1024


def _validate_text_stream(source: Path) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")()
    saw_bytes = False
    try:
        with source.open("rb") as stream:
            while chunk := stream.read(VALIDATION_CHUNK_BYTES):
                saw_bytes = True
                if b"\x00" in chunk:
                    raise MalformedInput("CSV contains binary data")
                decoder.decode(chunk)
        decoder.decode(b"", final=True)
    except MalformedInput:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise MalformedInput(f"CSV is not valid UTF-8 text: {exc}") from exc
    if not saw_bytes:
        raise MalformedInput("CSV is empty")


class CsvAdapter:
    def inspect(self, source: Path, session_dir: Path) -> list[TableHandle]:
        del session_dir
        _validate_text_stream(source)
        scan = f"read_csv({quote_literal(source)}, all_varchar=true, filename=true)"
        return [TableHandle("data", f"SELECT * FROM {scan}", "csv:line")]
