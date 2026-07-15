from __future__ import annotations

from data_workbench.domain.finding import Detector, Severity
from data_workbench.domain.profile import ColumnProfile, DatasetProfile
from data_workbench.findings.base import SqlDetector

MAX_CATEGORY_CARDINALITY = 20


def _rare_category_predicate(quoted: str, scan_sql: str) -> str:
    return (
        f"{quoted} IN (SELECT {quoted} FROM ({scan_sql})"
        f" WHERE {quoted} IS NOT NULL"
        f" GROUP BY {quoted} HAVING count(*) = 1)"
    )


def _categorical_columns_only(column: ColumnProfile, profile: DatasetProfile) -> bool:
    return (
        2 <= column.distinct_count <= MAX_CATEGORY_CARDINALITY
        and profile.row_count >= column.distinct_count * 2
    )


DETECTORS: tuple[Detector, ...] = (
    SqlDetector(
        rule_id="statistics.rare_category",
        rule_version=1,
        category="statistics",
        severity=Severity.info,
        confidence=0.5,
        predicate=_rare_category_predicate,
        suggestion=None,
        risk="informational",
        applies=_categorical_columns_only,
    ),
)
