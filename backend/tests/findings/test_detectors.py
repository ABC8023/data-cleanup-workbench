from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from data_workbench.domain.finding import Finding, Severity
from data_workbench.domain.profile import DatasetProfile
from data_workbench.engine.duckdb_runtime import DuckDBRuntime
from data_workbench.findings.registry import FindingRegistry
from data_workbench.ingest.base import TableHandle
from data_workbench.profiling.profiler import Profiler

ROWS = [
    ("x1", "N/A", "2026-01-02", "RM 1,200", " padded", "KUL", "A", "a@b.com"),
    ("x2", "null", "3/4/2026", "$5", "ok", "kul", "A", "bad-email"),
    ("x3", "-", "2026-05-06", "10", " x ", "JHB", "A", "c@d.org"),
    ("x4", "ok", "2026-07-08", "RM 3", "y", "KUL", "A", "e@f.io"),
    ("x5", "fine", "9/10/2026", "€7", "z", "kul", "B", "g@h.com"),
    ("x6", "good", "2026-11-12", "8", "a", "KUL", "A", "i@j.net"),
    ("x7", "great", "2026-12-13", "9", "b", "kul", "A", "k@l.co"),
    ("x8", "super", "2026-01-14", "11", "c", "KUL", "A", "m@n.dev"),
]


@pytest.fixture
def profiled_quality_fixture(
    tmp_path: Path,
) -> tuple[duckdb.DuckDBPyConnection, TableHandle, DatasetProfile]:
    connection = DuckDBRuntime("512MB", 1).connect(tmp_path / "session")
    connection.execute(
        'CREATE TABLE quality (" " VARCHAR, null_tokens VARCHAR,'
        " mixed_dates VARCHAR, currency_text VARCHAR, spaced_text VARCHAR,"
        " case_variants VARCHAR, rare_category VARCHAR, contact_email VARCHAR)"
    )
    for row in ROWS:
        connection.execute(
            "INSERT INTO quality VALUES (?, ?, ?, ?, ?, ?, ?, ?)", list(row)
        )
    handle = TableHandle("data", "SELECT * FROM quality", "test:quality")
    profile = Profiler(sample_rows=50).profile(
        connection, handle, "fixture-sha256", lambda: None
    )
    return connection, handle, profile


@pytest.mark.parametrize(
    ("column", "rule_id"),
    [
        (" ", "schema.empty_header"),
        ("null_tokens", "completeness.null_token"),
        ("mixed_dates", "validity.mixed_date"),
        ("currency_text", "validity.numeric_symbol"),
        ("contact_email", "validity.invalid_email"),
        ("spaced_text", "consistency.whitespace"),
        ("case_variants", "consistency.case_variant"),
        ("rare_category", "statistics.rare_category"),
    ],
)
def test_fixture_emits_expected_rule(
    profiled_quality_fixture: tuple[
        duckdb.DuckDBPyConnection, TableHandle, DatasetProfile
    ],
    column: str,
    rule_id: str,
) -> None:
    findings = FindingRegistry.default().detect(*profiled_quality_fixture)

    assert any(
        finding.rule_id == rule_id and column in finding.columns
        for finding in findings
    )


def test_finding_identity_and_order_are_stable(
    profiled_quality_fixture: tuple[
        duckdb.DuckDBPyConnection, TableHandle, DatasetProfile
    ],
) -> None:
    connection, handle, profile = profiled_quality_fixture
    registry = FindingRegistry.default()

    first = registry.detect(connection, handle, profile)
    second = FindingRegistry(tuple(reversed(registry.detectors))).detect(
        connection, handle, profile
    )

    assert [finding.id for finding in first] == [finding.id for finding in second]
    assert all(
        finding.affected_ratio == finding.affected_row_count / profile.row_count
        for finding in first
    )
    assert all(len(finding.examples) <= 10 for finding in first)
    severities = [int(finding.severity) for finding in first]
    assert severities == sorted(severities, reverse=True)


def test_findings_carry_evidence_and_bounded_sanitized_examples(
    profiled_quality_fixture: tuple[
        duckdb.DuckDBPyConnection, TableHandle, DatasetProfile
    ],
) -> None:
    findings = FindingRegistry.default().detect(*profiled_quality_fixture)
    by_rule = {finding.rule_id: finding for finding in findings}

    null_token = by_rule["completeness.null_token"]
    assert null_token.affected_row_count == 3
    assert {example["value"] for example in null_token.examples} == {
        "N/A",
        "null",
        "-",
    }
    assert "predicate" in null_token.evidence

    mixed_date = by_rule["validity.mixed_date"]
    assert mixed_date.evidence["iso_count"] == 6
    assert mixed_date.evidence["slash_count"] == 2
    assert mixed_date.affected_row_count == 8

    invalid_email = by_rule["validity.invalid_email"]
    assert invalid_email.affected_row_count == 1
    assert invalid_email.examples == [
        {"column": "contact_email", "value": "bad-email"}
    ]


def test_informational_findings_never_suggest_operations(
    profiled_quality_fixture: tuple[
        duckdb.DuckDBPyConnection, TableHandle, DatasetProfile
    ],
) -> None:
    findings = FindingRegistry.default().detect(*profiled_quality_fixture)

    rare = [f for f in findings if f.rule_id == "statistics.rare_category"]
    assert rare
    assert all(finding.suggested_operation is None for finding in rare)
    assert all(finding.risk_level == "informational" for finding in rare)
    assert all(finding.severity == Severity.info for finding in rare)


def test_findings_round_trip_through_json(
    profiled_quality_fixture: tuple[
        duckdb.DuckDBPyConnection, TableHandle, DatasetProfile
    ],
) -> None:
    findings = FindingRegistry.default().detect(*profiled_quality_fixture)

    assert findings
    for finding in findings:
        assert Finding.model_validate(finding.model_dump(mode="json")) == finding
