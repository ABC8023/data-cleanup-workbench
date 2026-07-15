# Task 7 Report: Typed Recipes and Transformation Registry

## Status

DONE

## Implementation

- `domain/recipe.py`: discriminated `RecipeStep` union (`rename_column`,
  `normalize_text`, `parse_date`, `cast_number`, `replace_value`, `drop_column`,
  `exact_deduplicate`, `apply_duplicate_decision`) with `extra="forbid"`, frozen
  models, per-step `on_error` (`preserve`/`set_null`/`quarantine`), and a
  `Recipe` model enforcing version 1 and unique step IDs. Rename requires
  exactly one column; parse_date requires at least one format.
- `recipes/compiled.py`: `CompiledOperation(sql, parameters, error_query,
  error_parameters)` plus shared `SELECT * REPLACE` projection and error-count
  helpers, so transforms never need to enumerate the input schema.
- `recipes/text.py`: `normalize_text` (trim/case, idempotent) and
  `replace_value` (`IS NOT DISTINCT FROM` with bound parameters; either side
  may be NULL).
- `recipes/casting.py`: `parse_date` (`try_strptime` across bound format
  parameters, normalized to ISO dates) and `cast_number` (currency/space
  stripping honoring `.`/`,` decimal separators; integers require integral
  values because DuckDB otherwise rounds `'12.5'` to 13). Both emit
  quarantine error queries counting unconvertible rows.
- `recipes/rows.py`: `drop_column` (`* EXCLUDE`), `rename_column`
  (`* RENAME`), `exact_deduplicate` (`row_number()` + `QUALIFY` keep
  first/last per key; `SELECT DISTINCT` for full-row), and
  `apply_duplicate_decision` (`keep_separate` compiles as identity;
  `remove_record`/`merge_fields` raise typed `UnsupportedDecisionContext`
  until the Task 9 duplicate engine supplies reviewed group context).
- `recipes/registry.py`: `OPERATIONS` dispatch, `compile_step`, and
  `compile_recipe`, which folds ordered steps into one nested SELECT while
  accumulating bound parameters in SQL text order (each step's placeholders
  precede its wrapped input) and collecting per-step quarantine error queries.

## Verification

- `backend/tests/recipes/test_schema.py`: unknown operations and injected extra
  fields rejected, duplicate step IDs fail, rename arity, empty formats fail,
  YAML round-trip preserves models and ordering.
- `backend/tests/recipes/test_operations.py`: normalizer idempotence; date
  parsing under preserve/set_null; currency and separator normalization for
  integers/decimals including European formats; NULL-aware replacement;
  quarantine error-query counts; drop/rename schema shaping; keep-first/last
  and full-row deduplication; typed duplicate-decision error; multi-step
  recipe compilation with correct parameter ordering.
- Full backend suite (120 tests), `ruff check`, `mypy backend/src` all pass.

## Commit

- `feat: add safe typed cleanup recipes`
