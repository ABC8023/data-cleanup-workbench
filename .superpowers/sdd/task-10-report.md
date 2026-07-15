# Task 10 Report: Reports, Dictionary, and Output Manifest

## Status

DONE

## Implementation

- `domain/artifact.py`: `ArtifactRecord` (fixed kind-based ids, filename,
  SHA-256, size) and `OutputManifest` (source fingerprint, recipe hash, app
  version, operation versions, row reconciliation, sorted artifacts,
  `state="complete"`).
- `artifacts/report.py`: deterministic quality-report builder (columns sorted
  by name; findings sorted by severity desc / rule / columns; no timestamps)
  rendered as canonical sorted-key JSON and autoescaped Jinja2 HTML.
- `artifacts/dictionary.py`: dictionary builder merging profile columns with
  user-reviewed descriptions, rendered as canonical JSON and a Markdown table
  (pipe/newline-escaped cells).
- `artifacts/manifest.py`: `ArtifactService.build(session_dir, fingerprint)`
  requires profile + findings + execution (typed `ArtifactBuildError` → 409),
  durably writes report/dictionary artifacts plus `manifest.json`, and records
  checksums for generated artifacts, the executed `recipe.yaml`, and the
  cleaned/quarantine outputs. Reviewed dictionary descriptions persist in
  `dictionary-reviewed.json`, never mutating the profile.
- Recipe persistence: the execute job now saves the executed recipe as
  `recipe.yaml` (sorted-key-stable YAML via `SessionRepository.save_recipe`)
  so the manifest's `recipe_hash` is reproducible.
- API (`api/routes/artifacts.py`): `POST /api/sessions/{id}/artifacts`
  (build), `GET .../artifacts` (manifest), `GET .../artifacts/{artifact_id}`
  (download by fixed id only — never caller paths — with
  `Content-Disposition`), and `GET`/`PUT .../dictionary` for reviewed
  descriptions. All token-authenticated.

## Verification

- `backend/tests/artifacts/test_artifacts.py` with golden files under
  `backend/tests/artifacts/golden/`: byte-exact report.json and dictionary.md,
  deterministic rebuilds with verified checksums and sorted kinds, HTML
  escaping of hostile example values, reviewed descriptions flowing into the
  dictionary, typed failure for unexecuted sessions.
- `backend/tests/api/test_artifact_routes.py`: full upload → profile →
  execute → dictionary edit → build → list → download flow, 404 for unknown
  or traversal-shaped artifact ids, 409 before execution, 401 without token.
- Full backend suite (144 tests), `ruff check`, `mypy backend/src` all pass.
