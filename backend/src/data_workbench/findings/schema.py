from __future__ import annotations

from dataclasses import dataclass

import duckdb

from data_workbench.domain.finding import Detector, Finding, Severity
from data_workbench.domain.profile import DatasetProfile
from data_workbench.findings.base import stable_finding_id
from data_workbench.ingest.base import SYSTEM_COLUMNS, TableHandle


@dataclass(frozen=True)
class EmptyHeaderDetector:
    rule_id: str = "schema.empty_header"
    rule_version: int = 1

    def detect(
        self,
        connection: duckdb.DuckDBPyConnection,
        handle: TableHandle,
        profile: DatasetProfile,
    ) -> list[Finding]:
        del connection
        findings: list[Finding] = []
        for column in profile.columns:
            if column.name in SYSTEM_COLUMNS or column.name.strip():
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
                    category="schema",
                    severity=Severity.error,
                    table=handle.name,
                    columns=[column.name],
                    affected_row_count=profile.row_count,
                    affected_ratio=1.0 if profile.row_count else 0.0,
                    evidence={"header": column.name},
                    examples=[],
                    confidence=1.0,
                    suggested_operation={"operation": "rename_column"},
                    risk_level="review_required",
                    provenance={"source": handle.source_locator},
                )
            )
        return findings


DETECTORS: tuple[Detector, ...] = (EmptyHeaderDetector(),)
