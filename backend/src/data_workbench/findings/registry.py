from __future__ import annotations

import duckdb

from data_workbench.domain.finding import Detector, Finding
from data_workbench.domain.profile import DatasetProfile
from data_workbench.findings import (
    completeness,
    consistency,
    schema,
    statistics,
    validity,
)
from data_workbench.ingest.base import TableHandle


class FindingRegistry:
    def __init__(self, detectors: tuple[Detector, ...]) -> None:
        self.detectors = detectors

    @classmethod
    def default(cls) -> FindingRegistry:
        return cls(
            schema.DETECTORS
            + completeness.DETECTORS
            + validity.DETECTORS
            + consistency.DETECTORS
            + statistics.DETECTORS
        )

    def detect(
        self,
        connection: duckdb.DuckDBPyConnection,
        handle: TableHandle,
        profile: DatasetProfile,
    ) -> list[Finding]:
        findings = [
            finding
            for detector in self.detectors
            for finding in detector.detect(connection, handle, profile)
        ]
        return sorted(
            findings,
            key=lambda finding: (
                -int(finding.severity),
                -finding.affected_ratio,
                finding.rule_id,
                tuple(finding.columns),
            ),
        )
