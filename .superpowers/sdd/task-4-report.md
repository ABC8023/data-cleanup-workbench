# Task 4 Report: Dataset Profiler

## Status

DONE

## Implementation

- Added frozen `ColumnProfile` and `DatasetProfile` Pydantic models with
  non-negative count validation.
- Added `Profiler.profile(connection, handle, source_fingerprint, cancel_check)`
  built entirely on DuckDB aggregates (`count(*) FILTER`, `approx_count_distinct`,
  `min`/`max`) — no `fetchdf()` and no whole-relation materialization in Python.
- `cancel_check()` runs between every column so long profiles remain cancellable.
- Distinct counts are clamped to the non-null count so the approximate sketch can
  never report an impossible value.
- Examples come from a bounded, value-ordered sample (`ORDER BY value LIMIT
  sample_rows`, then `DISTINCT ... LIMIT 10`) so repeated profiling of the same
  source yields byte-identical JSON.
- Top values use `GROUP BY value ORDER BY count DESC, value ASC LIMIT 10` for a
  deterministic tie-break.
- `sampled` is set whenever the row count exceeds the profiler's sample budget.

## Verification

- `backend/tests/profiling/test_profiler.py`: contract test (row counts, nulls,
  distinct, examples), types/extremes/top values, cancellation between columns,
  repeat-determinism, sampled flag, hostile quoted column names.
- `backend/tests/profiling/test_profiler_properties.py`: Hypothesis property
  tests over `list[int | None]` asserting null-count exactness, distinct/null
  bounds, example ordering and caps, top-value caps, and profile determinism.
- Full backend suite, `ruff check`, and `mypy backend/src` all pass.

## Commit

- `7dc2b87 feat: profile datasets with bounded memory`

## Environment note

This task was executed on a new machine (Windows 11, user `User`). The committed
`.venv` pointed at the previous machine's interpreter, so verification ran with a
uv-managed CPython 3.12.13 plus the vendored `.deps` directory
(`PYTHONPATH=.deps;backend/src`). Behavior and gates are unchanged.
