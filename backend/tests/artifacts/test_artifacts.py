from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from data_workbench.artifacts.manifest import (
    ArtifactBuildError,
    ArtifactService,
    artifact_path,
    load_manifest,
    save_reviewed_descriptions,
)

GOLDEN_DIR = Path(__file__).parent / "golden"
FINGERPRINT = "fixture-sha256"

PROFILE = {
    "source_fingerprint": FINGERPRINT,
    "table": "data",
    "row_count": 10,
    "sampled": False,
    "columns": [
        {
            "name": "customer_id",
            "inferred_type": "VARCHAR",
            "null_count": 1,
            "distinct_count": 8,
            "min_value": "c1",
            "max_value": "c9",
            "examples": ["c1", "c2"],
            "top_values": [["c1", 2]],
        },
        {
            "name": "amount",
            "inferred_type": "VARCHAR",
            "null_count": 0,
            "distinct_count": 9,
            "min_value": "10",
            "max_value": "99",
            "examples": ["10", "20"],
            "top_values": [],
        },
    ],
}

FINDINGS = [
    {
        "id": "f1",
        "rule_id": "completeness.null_token",
        "rule_version": 1,
        "category": "completeness",
        "severity": 2,
        "table": "data",
        "columns": ["customer_id"],
        "affected_row_count": 2,
        "affected_ratio": 0.2,
        "evidence": {"predicate": "customer_id IS NOT NULL"},
        "examples": [
            {"column": "customer_id", "value": "<script>alert(1)</script>"}
        ],
        "confidence": 0.9,
        "suggested_operation": None,
        "risk_level": "review_required",
        "provenance": {"source": "csv:line"},
    }
]


def build_completed_session(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    outputs = directory / "outputs"
    outputs.mkdir(exist_ok=True)
    (outputs / "cleaned.parquet").write_bytes(b"PAR1-cleaned")
    (outputs / "quarantine.parquet").write_bytes(b"PAR1-quarantine")
    execution = {
        "cleaned_path": str(outputs / "cleaned.parquet"),
        "quarantine_path": str(outputs / "quarantine.parquet"),
        "input_rows": 10,
        "output_rows": 8,
        "removed_rows": 1,
        "quarantined_rows": 1,
    }
    (directory / "profile.json").write_text(json.dumps(PROFILE), encoding="utf-8")
    (directory / "findings.json").write_text(
        json.dumps(FINDINGS), encoding="utf-8"
    )
    (directory / "execution.json").write_text(
        json.dumps(execution), encoding="utf-8"
    )
    (directory / "recipe.yaml").write_text(
        "recipe_version: 1\nsource_fingerprint: fixture-sha256\nsteps: []\n",
        encoding="utf-8",
    )
    return directory


@pytest.fixture
def completed_session(tmp_path: Path) -> Path:
    return build_completed_session(tmp_path / "session")


def test_builders_match_golden_files(completed_session: Path) -> None:
    manifest = ArtifactService().build(completed_session, FINGERPRINT)

    by_kind = {record.kind: record for record in manifest.artifacts}
    artifacts_dir = completed_session / "artifacts"
    report = (artifacts_dir / by_kind["report_json"].filename).read_text(
        encoding="utf-8"
    )
    dictionary = (artifacts_dir / by_kind["dictionary_md"].filename).read_text(
        encoding="utf-8"
    )
    assert report == (GOLDEN_DIR / "report.json").read_text(encoding="utf-8")
    assert dictionary == (GOLDEN_DIR / "dictionary.md").read_text(
        encoding="utf-8"
    )
    assert manifest.row_reconciliation == {
        "input": 10,
        "output": 8,
        "removed": 1,
        "quarantined": 1,
    }


def test_manifest_is_deterministic_with_verified_checksums(
    completed_session: Path,
) -> None:
    service = ArtifactService()

    first = service.build(completed_session, FINGERPRINT)
    second = service.build(completed_session, FINGERPRINT)

    assert first.model_dump() == second.model_dump()
    assert first.state == "complete"
    assert first.recipe_hash
    assert first.app_version == "0.1.0"
    assert first.operation_versions["normalize_text"] == 1
    kinds = [record.kind for record in first.artifacts]
    assert kinds == sorted(kinds)
    assert {"cleaned", "quarantine", "recipe", "report_html"} <= set(kinds)
    for record in first.artifacts:
        path = artifact_path(completed_session, record)
        assert record.id == record.kind
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record.sha256
        assert path.stat().st_size == record.size_bytes
    assert load_manifest(completed_session) == first


def test_report_html_escapes_hostile_values(completed_session: Path) -> None:
    ArtifactService().build(completed_session, FINGERPRINT)

    html = (completed_session / "artifacts" / "report.html").read_text(
        encoding="utf-8"
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_reviewed_descriptions_flow_into_dictionary(
    completed_session: Path,
) -> None:
    save_reviewed_descriptions(
        completed_session, {"customer_id": "Primary customer key"}
    )

    ArtifactService().build(completed_session, FINGERPRINT)

    markdown = (completed_session / "artifacts" / "dictionary.md").read_text(
        encoding="utf-8"
    )
    assert "Primary customer key" in markdown


def test_build_requires_profiled_and_executed_session(tmp_path: Path) -> None:
    empty = tmp_path / "empty-session"
    empty.mkdir()

    with pytest.raises(ArtifactBuildError, match="executed"):
        ArtifactService().build(empty, FINGERPRINT)
