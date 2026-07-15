from __future__ import annotations

from pathlib import Path

import duckdb


class DuckDBRuntime:
    def __init__(self, memory_limit: str = "4GB", threads: int = 4) -> None:
        self.memory_limit = memory_limit
        self.threads = threads

    def connect(self, session_dir: Path) -> duckdb.DuckDBPyConnection:
        session_dir.mkdir(parents=True, exist_ok=True)
        temp_directory = session_dir / "duckdb.tmp"
        temp_directory.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(
            str(session_dir / "workbench.duckdb"),
            config={
                "allow_unsigned_extensions": "false",
                "memory_limit": self.memory_limit,
                "threads": str(self.threads),
                "temp_directory": str(temp_directory),
            },
        )
