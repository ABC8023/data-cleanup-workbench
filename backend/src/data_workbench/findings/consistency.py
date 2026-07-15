from __future__ import annotations

from data_workbench.domain.finding import Detector, Severity
from data_workbench.findings.base import SqlDetector


def _whitespace_predicate(quoted: str, scan_sql: str) -> str:
    del scan_sql
    text = f"CAST({quoted} AS VARCHAR)"
    return f"{quoted} IS NOT NULL AND {text} <> trim({text})"


def _case_variant_predicate(quoted: str, scan_sql: str) -> str:
    text = f"CAST({quoted} AS VARCHAR)"
    return (
        f"{quoted} IS NOT NULL AND lower({text}) IN ("
        f"SELECT lower({text}) FROM ({scan_sql}) WHERE {quoted} IS NOT NULL"
        f" GROUP BY lower({text}) HAVING count(DISTINCT {text}) > 1)"
    )


DETECTORS: tuple[Detector, ...] = (
    SqlDetector(
        rule_id="consistency.whitespace",
        rule_version=1,
        category="consistency",
        severity=Severity.warning,
        confidence=0.95,
        predicate=_whitespace_predicate,
        suggestion={"operation": "trim_whitespace"},
        risk="safe",
    ),
    SqlDetector(
        rule_id="consistency.case_variant",
        rule_version=1,
        category="consistency",
        severity=Severity.warning,
        confidence=0.8,
        predicate=_case_variant_predicate,
        suggestion={"operation": "set_case"},
        risk="review_required",
    ),
)
