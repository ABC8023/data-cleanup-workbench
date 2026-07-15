from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from data_workbench.artifacts.dictionary import (
    build_dictionary,
    render_dictionary_json,
    render_dictionary_markdown,
)
from data_workbench.artifacts.report import (
    build_report,
    render_report_html,
    render_report_json,
)
from data_workbench.domain.artifact import ArtifactKind, ArtifactRecord, OutputManifest
from data_workbench.recipes.registry import OPERATIONS

APP_VERSION = "0.1.0"
ARTIFACTS_DIRNAME = "artifacts"
MANIFEST_FILENAME = "manifest.json"
REVIEWED_DICTIONARY_FILENAME = "dictionary-reviewed.json"


class ArtifactBuildError(ValueError):
    """Raised when a session is not ready to produce artifacts."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_durable(path: Path, payload: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_reviewed_descriptions(session_dir: Path) -> dict[str, str]:
    path = session_dir / REVIEWED_DICTIONARY_FILENAME
    try:
        loaded = _load_json(path)
    except FileNotFoundError:
        return {}
    return {str(key): str(value) for key, value in loaded.items()}


def save_reviewed_descriptions(
    session_dir: Path, descriptions: dict[str, str]
) -> None:
    _write_durable(
        session_dir / REVIEWED_DICTIONARY_FILENAME,
        json.dumps(descriptions, indent=2, sort_keys=True) + "\n",
    )


class ArtifactService:
    def build(self, session_dir: Path, source_fingerprint: str) -> OutputManifest:
        try:
            profile = _load_json(session_dir / "profile.json")
            findings = _load_json(session_dir / "findings.json")
            execution = _load_json(session_dir / "execution.json")
        except FileNotFoundError as error:
            raise ArtifactBuildError(
                "artifacts require a profiled and executed session"
            ) from error
        artifacts_dir = session_dir / ARTIFACTS_DIRNAME
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        report = build_report(profile, findings)
        dictionary = build_dictionary(
            profile, load_reviewed_descriptions(session_dir)
        )
        generated: dict[ArtifactKind, tuple[str, str]] = {
            "report_json": ("report.json", render_report_json(report)),
            "report_html": ("report.html", render_report_html(report)),
            "dictionary_json": (
                "dictionary.json",
                render_dictionary_json(dictionary),
            ),
            "dictionary_md": (
                "dictionary.md",
                render_dictionary_markdown(dictionary),
            ),
        }
        records: list[ArtifactRecord] = []
        for kind, (filename, payload) in generated.items():
            destination = artifacts_dir / filename
            _write_durable(destination, payload)
            records.append(self._record(kind, filename, destination))

        recipe_path = session_dir / "recipe.yaml"
        recipe_hash = ""
        if recipe_path.exists():
            recipe_hash = _sha256_file(recipe_path)
            records.append(self._record("recipe", "recipe.yaml", recipe_path))
        cleaned_path = Path(str(execution["cleaned_path"]))
        if cleaned_path.exists():
            records.append(
                self._record("cleaned", cleaned_path.name, cleaned_path)
            )
        quarantine_value = execution.get("quarantine_path")
        if quarantine_value:
            quarantine_path = Path(str(quarantine_value))
            if quarantine_path.exists():
                records.append(
                    self._record(
                        "quarantine", quarantine_path.name, quarantine_path
                    )
                )

        manifest = OutputManifest(
            source_fingerprint=source_fingerprint,
            recipe_hash=recipe_hash,
            app_version=APP_VERSION,
            operation_versions={name: 1 for name in sorted(OPERATIONS)},
            row_reconciliation={
                "input": int(execution["input_rows"]),
                "output": int(execution["output_rows"]),
                "removed": int(execution["removed_rows"]),
                "quarantined": int(execution["quarantined_rows"]),
            },
            artifacts=sorted(records, key=lambda record: record.kind),
        )
        _write_durable(
            artifacts_dir / MANIFEST_FILENAME,
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True)
            + "\n",
        )
        return manifest

    def _record(
        self, kind: ArtifactKind, filename: str, path: Path
    ) -> ArtifactRecord:
        return ArtifactRecord(
            id=kind,
            kind=kind,
            filename=filename,
            sha256=_sha256_file(path),
            size_bytes=path.stat().st_size,
        )


def load_manifest(session_dir: Path) -> OutputManifest | None:
    path = session_dir / ARTIFACTS_DIRNAME / MANIFEST_FILENAME
    try:
        return OutputManifest.model_validate(_load_json(path))
    except FileNotFoundError:
        return None


def artifact_path(session_dir: Path, record: ArtifactRecord) -> Path:
    if record.kind in {"cleaned", "quarantine"}:
        return session_dir / "outputs" / record.filename
    if record.kind == "recipe":
        return session_dir / record.filename
    return session_dir / ARTIFACTS_DIRNAME / record.filename
