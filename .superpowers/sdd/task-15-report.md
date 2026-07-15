# Task 15 Report: Security, Packaging, E2E, and Benchmark

## Status

DONE (code + local verification); three items need CI/reference hardware —
see "Deferred to CI" below.

## Implementation

- Security (`core/security.py`, `api/app.py`,
  `backend/tests/security/test_local_security.py`):
  `validate_loopback_host` rejects non-loopback binds; an origin-enforcement
  middleware 403s any request whose Origin differs from the configured
  loopback origin; `Redactor`/`redact_mapping` strip sample/credential-marker
  keys (recursively) from logged context. The app factory now optionally
  mounts the built UI (`static_dir`, default `data_workbench/static`) while
  `/api/*` stays token-gated. Five security tests cover all of it.
- Launcher (`cli.py`, `pyproject.toml [project.scripts]`): `data-workbench`
  validates the loopback host, reserves an ephemeral port, generates a random
  token (a `--token` override exists for testing), starts Uvicorn with logging
  config disabled, and opens the browser at `/#token=...` — the fragment never
  reaches server logs, and the UI reads it once then strips it via
  `history.replaceState` (App.tsx updated accordingly).
- Benchmarks: `generate_dataset.py` deterministically writes a dirty CSV (+
  Parquet via DuckDB) with currency amounts, null tokens, mixed date formats,
  case/whitespace variants, invalid emails, rare categories, and ~1% exact
  duplicates. `run_benchmark.py` runs inspect → profile → findings → a
  canonical 4-step recipe (trim, parse dates, cast amounts with quarantine,
  full-row dedup) in-process, records machine metadata, wall time, OS-level
  peak RSS (K32GetProcessMemoryInfo / VmHWM / ru_maxrss), session disk bytes,
  reconciliation, and cleaned-file checksum; exits nonzero above the RSS
  budget or on reconciliation failure.
- Scripts: `build_frontend.py` (npm ci + build + copy dist →
  `data_workbench/static`) and `package.py` (build frontend, then PyInstaller
  single-folder bundle with static assets and duckdb collected).
- CI (`.github/workflows/ci.yml`): 3-OS matrix (pytest, ruff incl.
  benchmarks/scripts, mypy, vitest, build), Ubuntu Playwright E2E job
  (chromium only), 0.1 GB smoke benchmark with JSON artifact upload, and a
  manually-dispatched canonical 5 GB job pinned to the reference runner.
- E2E: `frontend/e2e/workbench.spec.ts` + `playwright.config.ts` — the config
  boots the real Python service (`--no-browser --token`) as the Playwright
  web server; the spec uploads a dirty fixture, profiles, reviews/approves the
  mixed-date transformation, executes, waits for downloads, and asserts the
  fixture checksum is unchanged. Vitest is scoped to `src/**` so it never
  collects Playwright specs.
- Bug found by the smoke benchmark: the dedup operation's internal row-id
  column collided with the executor's quarantine row id
  (both `__workbench_row_id`) — quarantine + dedup recipes failed to compile.
  Renamed to `__workbench_dedup_row_id`.

## Verification (local, this machine)

- Backend: 159 tests pass; ruff clean over backend + benchmarks + scripts;
  mypy clean (66 files). Frontend: 15 tests pass; tsc/vite build and eslint
  clean.
- Smoke benchmark (0.1 GB, seed 20260715, parquet input): 1,362,195 rows in
  11.5 s, peak RSS 550 MB (budget 6 GB), reconciliation exact
  (1,298,204 output + 12,850 removed + 51,141 quarantined), exit 0.
- Launcher smoke: served the built UI at `/` (200), `/api/health` 401 without
  token / 200 with token, 403 for `Origin: https://example.com`, and shut
  down cleanly.

## Deferred to CI / reference hardware

1. Playwright browser run (spec + config + CI job ready; browser binaries not
   downloaded on this machine).
2. PyInstaller packaging + per-platform smoke (script ready; needs
   `pip install pyinstaller` and the three CI OS runners).
3. Canonical 5 GB benchmark on the documented 8-core/16 GB reference machine
   (workflow-dispatch CI job ready; the 0.1 GB smoke validates the harness).
