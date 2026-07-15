from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Literal

import duckdb

from data_workbench.domain.finding import Finding, Severity
from data_workbench.domain.profile import ColumnProfile, DatasetProfile
from data_workbench.engine.sql import quote_identifier
from data_workbench.ingest.base import SYSTEM_COLUMNS, TableHandle

EXAMPLE_LIMIT = 10


def stable_finding_id(
    source_fingerprint: str,
    rule_id: str,
    rule_version: int,
    table: str,
    columns: list[str],
) -> str:
    material = "|".join(
        [source_fingerprint, rule_id, str(rule_version), table, *columns]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def bounded_examples(
    connection: duckdb.DuckDBPyConnection,
    scan_sql: str,
    column: str,
    predicate: str,
    limit: int = EXAMPLE_LIMIT,
) -> list[dict[str, str]]:
    quoted = quote_identifier(column)
    rows = connection.sql(
        f"SELECT DISTINCT CAST({quoted} AS VARCHAR) AS value"
        f" FROM ({scan_sql}) WHERE {predicate}"
        f" ORDER BY value NULLS FIRST LIMIT {limit}"
    ).fetchall()
    return [
        {"column": column, "value": "" if row[0] is None else str(row[0])}
        for row in rows
    ]


def _always(column: ColumnProfile, profile: DatasetProfile) -> bool:
    del column, profile
    return True


@dataclass(frozen=True)
class SqlDetector:
    """Per-column detector driven by one documented SQL boolean predicate."""

    rule_id: str
    rule_version: int
    category: str
    severity: Severity
    confidence: float
    predicate: Callable[[str, str], str]
    suggestion: dict[str, object] | None
    risk: Literal["safe", "review_required", "informational"]
    applies: Callable[[ColumnProfile, DatasetProfile], bool] = _always

    def detect(
        self,
        connection: duckdb.DuckDBPyConnection,
        handle: TableHandle,
        profile: DatasetProfile,
    ) -> list[Finding]:
        findings: list[Finding] = []
        for column in profile.columns:
            if column.name in SYSTEM_COLUMNS or not self.applies(column, profile):
                continue
            quoted = quote_identifier(column.name)
            predicate = self.predicate(quoted, handle.scan_sql)
            counted = connection.sql(
                f"SELECT count(*) FROM ({handle.scan_sql}) WHERE {predicate}"
            ).fetchone()
            count = int(counted[0]) if counted is not None else 0
            if not count:
                continue
            findings.append(
                Finding(
                    id=stable_finding_id(
                        profile.source_fingerprint,
                        self.rule_id,
                        self.rule_version,
                        handle.name,
                        [column.name],
                    ),
                    rule_id=self.rule_id,
                    rule_version=self.rule_version,
                    category=self.category,
                    severity=self.severity,
                    table=handle.name,
                    columns=[column.name],
                    affected_row_count=count,
                    affected_ratio=(
                        count / profile.row_count if profile.row_count else 0.0
                    ),
                    evidence={"predicate": predicate},
                    examples=bounded_examples(
                        connection, handle.scan_sql, column.name, predicate
                    ),
                    confidence=self.confidence,
                    suggested_operation=self.suggestion,
                    risk_level=self.risk,
                    provenance={"source": handle.source_locator},
                )
            )
        return findings
