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
        return self.inspect_declared(source, source.name, session_dir)

    def inspect_declared(
        self,
        source: Path,
        declared_filename: str,
        session_dir: Path,
    ) -> list[TableHandle]:
        suffix = Path(declared_filename).suffix.lower()
        adapter = self.adapters.get(suffix)
        if adapter is None:
            raise UnsupportedFormat(suffix)
        return adapter.inspect(source, session_dir)
