from __future__ import annotations

from data_workbench.domain.finding import Detector, Severity
from data_workbench.engine.sql import quote_literal
from data_workbench.findings.base import SqlDetector

NULL_TOKENS = ("null", "n/a", "na", "none", "-", "")


def _null_token_predicate(quoted: str, scan_sql: str) -> str:
    del scan_sql
    tokens = ", ".join(quote_literal(token) for token in NULL_TOKENS)
    return (
        f"{quoted} IS NOT NULL"
        f" AND trim(lower(CAST({quoted} AS VARCHAR))) IN ({tokens})"
    )


DETECTORS: tuple[Detector, ...] = (
    SqlDetector(
        rule_id="completeness.null_token",
        rule_version=1,
        category="completeness",
        severity=Severity.warning,
        confidence=0.9,
        predicate=_null_token_predicate,
        suggestion={"operation": "replace_value", "new": None},
        risk="review_required",
    ),
)
