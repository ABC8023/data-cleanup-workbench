# Data Cleanup Workbench

Local-first data profiling, cleanup, duplicate review, and reproducible
export workbench. Files up to 5 GB (CSV, JSON, NDJSON, Parquet, `.xlsx`) are
staged immutably, profiled with bounded memory in DuckDB, cleaned through
typed, previewed, explicitly approved operations, and exported with checksums
and full row reconciliation. No data leaves the machine; optional AI is
consent-gated behind an exact payload preview and disabled by default.

## Run

```bash
python -m pip install -e ".[dev]"
python scripts/build_frontend.py   # bundle the React UI (requires Node 24)
data-workbench                     # loopback server + browser, random token
```

## AI dictionary assist (optional, off by default)

The Data dictionary panel can ask Claude to draft column descriptions. It is
disabled unless you opt in at launch, and even then nothing is sent until you
approve the exact payload shown in the preview dialog.

```bash
# store your Anthropic API key once (or set ANTHROPIC_API_KEY instead)
keyring set data-cleanup-workbench ai_api_key

data-workbench --ai anthropic      # built-in Claude provider
data-workbench --ai-url https://…  # or your own endpoint speaking the same contract
```

A custom `--ai-url` endpoint receives the previewed JSON payload via POST
(bearer token from the same keyring entry) and must reply with
`{"columns": [{"name": …, "description": …}]}`.

## Develop

```bash
python -m pytest backend/tests -q
python -m ruff check backend/src backend/tests benchmarks scripts
python -m mypy backend/src
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

End-to-end: `python scripts/build_frontend.py`, then
`npm --prefix frontend exec playwright test`.

## Benchmark

```bash
python benchmarks/generate_dataset.py --size-gb 0.1 --seed 20260715
python benchmarks/run_benchmark.py \
  --input benchmarks/generated/canonical.parquet --max-rss-gb 6
```

The canonical run uses `--size-gb 5` on the reference machine (8 cores,
16 GB RAM, SSD) and must stay under 6 GB peak RSS.

## Layout

- `backend/src/data_workbench/` — FastAPI service: staging, ingest adapters,
  profiler, finding detectors, command edits, typed recipes with transactional
  execution, duplicate engine, artifacts, consent-gated AI gateway, CLI.
- `frontend/` — React workbench (upload, overview, findings review, recipe
  editor, duplicate review, dictionary, execution and downloads).
- `benchmarks/`, `scripts/`, `.github/workflows/ci.yml` — verification and
  packaging (`scripts/package.py` builds the PyInstaller bundle).
- `.superpowers/sdd/` — per-task execution reports.
