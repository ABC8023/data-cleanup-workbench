# Task 9 Report: Conservative Duplicate Detection

## Status

DONE

## Implementation

- `domain/duplicates.py`: `DuplicateConfig` (blocking columns, comparison
  weights, threshold), `DuplicateCandidate` (pair confidence + field-level
  evidence), `DuplicateDecision` (typed reviewed actions), and `DuplicateGroup`
  (stable id, row ids, candidates, display values, `decision=None` always —
  fuzzy duplicates are never resolved automatically).
- `duplicates/engine.py`: `DuplicateEngine.find_fuzzy` validates the
  configuration (typed `InvalidDuplicateConfig` for missing blocking keys,
  missing/unknown columns, non-positive weights), builds normalized blocking
  keys in SQL (lower/trim, NUL-separated), fetches only rows in blocks of
  size 2..max_block_rows with a bounded total fetch, scores in-block pairs
  with RapidFuzz `token_sort_ratio` + `default_process` (case/spacing
  normalization; both-NULL = 1.0, one-NULL = 0.0), combines documented weights
  into a confidence, accepts pairs at/above the threshold, and groups them via
  union-find with deterministic ordering and SHA-256-derived group ids.
  `find_exact` groups identical rows over user columns via GROUP BY/HAVING
  with confidence 1.0. Both exclude scan-provenance columns. Row ids are
  `row_number()` in scan order (DuckDB preserves insertion order by default).
- API (`api/routes/sessions.py`): `POST /api/sessions/{id}/duplicates/fuzzy`
  (config + max_candidates) and `POST /api/sessions/{id}/duplicates/exact`
  (columns), both resolving the current table state (post-edit) and mapping
  `InvalidDuplicateConfig` to 400.

## Verification

- `backend/tests/duplicates/test_duplicate_engine.py`: blocking before scoring
  (identical name in a different block never compared), case/spacing variants
  grouped, no group ever carries a decision, deterministic repeated searches,
  typed configuration errors, block-size and candidate caps bounding the
  search, exact grouping with confidence 1.0.
- Full backend suite (137 tests), `ruff check`, `mypy backend/src` all pass.

## Notes

- RapidFuzz does NOT normalize case by default; `utils.default_process` is
  required for "John Smith" vs "JOHN SMITH" to score 1.0.
- The test file is named `test_duplicate_engine.py` because pytest (no
  test-package `__init__.py`) rejects duplicate basenames across test dirs.
- `apply_duplicate_decision` execution (remove_record/merge_fields) still
  raises a typed error in the recipe compiler; wiring reviewed decisions into
  execution is the follow-up now that groups and row ids exist.
