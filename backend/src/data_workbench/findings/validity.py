from __future__ import annotations

from dataclasses import dataclass

import duckdb

from data_workbench.domain.finding import Detector, Finding, Severity
from data_workbench.domain.profile import ColumnProfile, DatasetProfile
from data_workbench.engine.sql import quote_identifier, quote_literal
from data_workbench.findings.base import SqlDetector, bounded_examples, stable_finding_id
from data_workbench.ingest.base import SYSTEM_COLUMNS, TableHandle

ISO_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
SLASH_DATE_PATTERN = r"^\d{1,2}/\d{1,2}/\d{4}$"
CURRENCY_PATTERN = r"^\s*(RM|[$€£])\s*-?[0-9][0-9.,]*\s*$"
EMAIL_PATTERN = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"


@dataclass(frozen=True)
class MixedDateDetector:
    rule_id: str = "validity.mixed_date"
    rule_version: int = 1

    def detect(
        self,
        connection: duckdb.DuckDBPyConnection,
        handle: TableHandle,
        profile: DatasetProfile,
    ) -> list[Finding]:
        findings: list[Finding] = []
        iso = quote_literal(ISO_DATE_PATTERN)
        slash = quote_literal(SLASH_DATE_PATTERN)
        for column in profile.columns:
            if column.name in SYSTEM_COLUMNS:
                continue
            text = f"CAST({quote_identifier(column.name)} AS VARCHAR)"
            counted = connection.sql(
                f"SELECT count(*) FILTER (WHERE regexp_matches({text}, {iso})),"
                f" count(*) FILTER (WHERE regexp_matches({text}, {slash}))"
                f" FROM ({handle.scan_sql})"
            ).fetchone()
            if counted is None:
                continue
            iso_count, slash_count = int(counted[0]), int(counted[1])
            if not iso_count or not slash_count:
                continue
            predicate = (
                f"regexp_matches({text}, {iso})"
                f" OR regexp_matches({text}, {slash})"
            )
            affected = iso_count + slash_count
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
                    category="validity",
                    severity=Severity.warning,
                    table=handle.name,
                    columns=[column.name],
                    affected_row_count=affected,
                    affected_ratio=(
                        affected / profile.row_count if profile.row_count else 0.0
                    ),
                    evidence={
                        "predicate": predicate,
                        "iso_count": iso_count,
                        "slash_count": slash_count,
                    },
                    examples=bounded_examples(
                        connection, handle.scan_sql, column.name, predicate
                    ),
                    confidence=0.8,
                    suggested_operation={"operation": "parse_date"},
                    risk_level="review_required",
                    provenance={"source": handle.source_locator},
                )
            )
        return findings


def _numeric_symbol_predicate(quoted: str, scan_sql: str) -> str:
    del scan_sql
    return (
        f"regexp_matches(CAST({quoted} AS VARCHAR),"
        f" {quote_literal(CURRENCY_PATTERN)})"
    )


def _invalid_email_predicate(quoted: str, scan_sql: str) -> str:
    del scan_sql
    return (
        f"{quoted} IS NOT NULL AND NOT regexp_matches("
        f"CAST({quoted} AS VARCHAR), {quote_literal(EMAIL_PATTERN)})"
    )


def _email_columns_only(column: ColumnProfile, profile: DatasetProfile) -> bool:
    del profile
    return "email" in column.name.lower()


DETECTORS: tuple[Detector, ...] = (
    MixedDateDetector(),
    SqlDetector(
        rule_id="validity.numeric_symbol",
        rule_version=1,
        category="validity",
        severity=Severity.warning,
        confidence=0.85,
        predicate=_numeric_symbol_predicate,
        suggestion={"operation": "cast_number"},
        risk="review_required",
    ),
    SqlDetector(
        rule_id="validity.invalid_email",
        rule_version=1,
        category="validity",
        severity=Severity.warning,
        confidence=0.7,
        predicate=_invalid_email_predicate,
        suggestion=None,
        risk="informational",
        applies=_email_columns_only,
    ),
)
