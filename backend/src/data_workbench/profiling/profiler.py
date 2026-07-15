from __future__ import annotations

from typing import Callable

import duckdb

from data_workbench.domain.profile import ColumnProfile, DatasetProfile
from data_workbench.engine.sql import quote_identifier
from data_workbench.ingest.base import SYSTEM_COLUMNS, TableHandle

EXAMPLE_LIMIT = 10
TOP_VALUE_LIMIT = 10


class Profiler:
    def __init__(self, sample_rows: int = 10_000) -> None:
        self.sample_rows = sample_rows

    def profile(
        self,
        connection: duckdb.DuckDBPyConnection,
        handle: TableHandle,
        source_fingerprint: str,
        cancel_check: Callable[[], None],
    ) -> DatasetProfile:
        view = f"({handle.scan_sql})"
        counted = connection.sql(f"SELECT count(*) FROM {view}").fetchone()
        row_count = int(counted[0]) if counted is not None else 0
        described = connection.sql(f"DESCRIBE SELECT * FROM {view}").fetchall()

        columns: list[ColumnProfile] = []
        for name, inferred_type, *_ in described:
            # Scan-provenance columns carry staged local paths; they are an
            # ingestion detail, not user data.
            if str(name) in SYSTEM_COLUMNS:
                continue
            cancel_check()
            columns.append(
                self._profile_column(connection, view, str(name), str(inferred_type), row_count)
            )
        return DatasetProfile(
            source_fingerprint=source_fingerprint,
            table=handle.name,
            row_count=row_count,
            columns=columns,
            sampled=row_count > self.sample_rows,
        )

    def _profile_column(
        self,
        connection: duckdb.DuckDBPyConnection,
        view: str,
        name: str,
        inferred_type: str,
        row_count: int,
    ) -> ColumnProfile:
        quoted = quote_identifier(name)
        aggregated = connection.sql(
            f"""
            SELECT count(*) FILTER (WHERE {quoted} IS NULL),
                   approx_count_distinct({quoted}),
                   CAST(min({quoted}) AS VARCHAR),
                   CAST(max({quoted}) AS VARCHAR)
            FROM {view}
            """
        ).fetchone()
        if aggregated is None:
            raise RuntimeError("column aggregation returned no row")
        null_count = int(aggregated[0])
        non_null_count = row_count - null_count
        distinct_count = min(int(aggregated[1]), non_null_count)
        min_value = None if aggregated[2] is None else str(aggregated[2])
        max_value = None if aggregated[3] is None else str(aggregated[3])

        # Examples come from a bounded, value-ordered sample so repeated profiling
        # of the same source yields byte-identical output.
        examples = [
            str(row[0])
            for row in connection.sql(
                f"""
                SELECT DISTINCT sampled.value
                FROM (
                    SELECT CAST({quoted} AS VARCHAR) AS value
                    FROM {view}
                    WHERE {quoted} IS NOT NULL
                    ORDER BY value
                    LIMIT {self.sample_rows}
                ) AS sampled
                ORDER BY sampled.value
                LIMIT {EXAMPLE_LIMIT}
                """
            ).fetchall()
        ]
        top_values = [
            (str(row[0]), int(row[1]))
            for row in connection.sql(
                f"""
                SELECT CAST({quoted} AS VARCHAR) AS value, count(*) AS occurrences
                FROM {view}
                WHERE {quoted} IS NOT NULL
                GROUP BY value
                ORDER BY occurrences DESC, value ASC
                LIMIT {TOP_VALUE_LIMIT}
                """
            ).fetchall()
        ]
        return ColumnProfile(
            name=name,
            inferred_type=inferred_type,
            null_count=null_count,
            distinct_count=distinct_count,
            min_value=min_value,
            max_value=max_value,
            examples=examples,
            top_values=top_values,
        )
