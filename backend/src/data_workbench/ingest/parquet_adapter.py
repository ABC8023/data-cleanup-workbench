from __future__ import annotations

from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from data_workbench.engine.sql import quote_literal
from data_workbench.ingest.base import MalformedInput, TableHandle


class ParquetAdapter:
    def inspect(self, source: Path, session_dir: Path) -> list[TableHandle]:
        del session_dir
        try:
            pq.ParquetFile(source)
        except (OSError, pa.ArrowException) as exc:
            raise MalformedInput(f"invalid Parquet input: {exc}") from exc
        scan = f"read_parquet({quote_literal(source)}, filename=true)"
        return [TableHandle("data", f"SELECT * FROM {scan}", "parquet:row")]
