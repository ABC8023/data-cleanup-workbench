# Task 8 Report: Preview and Transactional Recipe Execution

## Status

DONE

## Key design decisions

- **Literal inlining replaced bound parameters.** `COPY (SELECT ...) TO` cannot
  bind prepared parameters, and parameter ordering across nested step chains
  was fragile. All recipe values now inline through the centralized
  `quote_literal` helper (the sanctioned escape path), and `CompiledOperation`
  shrank to `(sql, failure_predicate)`.
- **Quarantine via row-id threading.** When any step uses
  `on_error="quarantine"`, execution materializes the visible input once into a
  temp table with a `__workbench_row_id` (so quarantine capture and cleaned
  output agree on row identity across queries — plain `row_number()` over a
  multi-threaded scan is not stable between queries). Each quarantine step
  filters its failing rows out of the chain; the quarantine file is the union
  of failing row ids joined back to the original visible schema. Full-row
  dedup is pinned to explicit columns when row ids are threaded so
  `SELECT DISTINCT *` cannot be poisoned by the synthetic id.
- **Scan-provenance columns (`filename`) are excluded** from previews, cleaned
  output, and quarantine output, matching the edit engine's behavior.

## Implementation

- `recipes/executor.py`: `RecipeExecutor.preview` samples a bounded relation
  (base LIMIT plus optional capped affected-row predicates), compiles the full
  ordered chain over the sample, and reports before/after rows, schemas, null
  deltas, row-count delta, and validation failures (per-step quarantine counts;
  compile errors return a failure note instead of raising).
  `RecipeExecutor.execute` writes `cleaned.partial.<ext>` (and
  `quarantine.partial.<ext>`), checks cancellation between phases, validates
  output readability by re-reading the partial through DuckDB, reconciles
  `input = output + removed + quarantined` (rejecting unexplained row loss when
  no row-removing step exists), fsyncs, and promotes via `os.replace`. Partials
  are always removed on any failure; the quarantine file is produced only when
  rows were actually quarantined.
- `recipes/registry.py`: `compile_chain(recipe, input_sql, exclude_failures)`
  returns per-step `CompiledStep(input_sql, output_sql, failure_predicate)`;
  `compile_recipe` returns the final SELECT.
- API (`api/routes/sessions.py`):
  - `POST /api/sessions/{id}/recipe/preview` — no side effects.
  - `POST /api/sessions/{id}/recipe/execute` — requires `approved=true` (400
    otherwise) and a recipe fingerprint matching the session source (409
    otherwise); runs as a cancellable job; `ExecutionError` maps to the
    sanitized `execution_failed` job code; result persisted durably to
    `execution.json`.
  - `GET /api/sessions/{id}/execution` — returns the persisted result.
  - Recipes execute against the current table state (chained on applied edits
    via `resolve_handle`).

## Verification

- `backend/tests/recipes/test_executor.py`: preview null deltas/schema changes,
  quarantine and compile-failure validation notes, output promotion with
  source immutability, quarantined-row capture with original values,
  dedup-removed reconciliation, CSV output, failed execution removing partials,
  cancellation leaving no outputs.
- `backend/tests/api/test_recipe_execution.py`: preview without side effects,
  approval and fingerprint gating, end-to-end execution with persisted results
  and retry, typed rejection of unknown operations (422), 404/401 handling.
- Full backend suite (131 tests), `ruff check`, `mypy backend/src` all pass.
