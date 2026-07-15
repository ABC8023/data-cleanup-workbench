from __future__ import annotations

from pathlib import Path

from data_workbench.ingest.base import Adapter, TableHandle, UnsupportedFormat
from data_workbench.ingest.csv_adapter import CsvAdapter
from data_workbench.ingest.excel_adapter import ExcelAdapter
from data_workbench.ingest.json_adapter import JsonAdapter
from data_workbench.ingest.parquet_adapter import ParquetAdapter


class AdapterRegistry:
    adapters: dict[str, Adapter] = {
        ".csv": CsvAdapter(),
        ".json": JsonAdapter(False),
        ".ndjson": JsonAdapter(True),
        ".parquet": ParquetAdapter(),
        ".xlsx": ExcelAdapter(),
    }

    def inspect(self, source: Path, session_dir: Path) -> list[TableHandle]:
        adapter = self.adapters.get(source.suffix.lower())
        if adapter is None:
            raise UnsupportedFormat(source.suffix)
        return adapter.inspect(source, session_dir)
