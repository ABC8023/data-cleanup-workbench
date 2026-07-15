# Feature Report: Command-Driven Column and Data Edits

## Status

DONE (user-requested feature outside the original task list)

## What it does

Users can edit columns or data with plain text commands. Commands are parsed by a
deterministic grammar into typed, discriminated Pydantic operations — never
arbitrary SQL or code — honoring the plan's recipe-safety constraint.

Supported commands:

- `rename column <name> to <name>`
- `drop column <name>`
- `replace '<value>' with '<value>' in column <name>` (either side may be `null`)
- `fill nulls in column <name> with '<value>'`
- `uppercase column <name>` / `lowercase column <name>`
- `trim whitespace in column <name>`

Column names may be double-quoted to include spaces; values are quoted or `null`.

## Architecture

- `domain/edit.py`: `EditCommand` discriminated union, `EditPreview`,
  `EditSample`, `AppliedEdit`.
- `editing/parser.py`: regex grammar → typed commands; unsupported input raises
  `UnsupportedCommand` listing the full grammar.
- `editing/engine.py`: compiles commands into a single SELECT over the current
  table handle using the centralized quoting helpers; previews report schema
  before/after, affected row counts, and bounded, deterministic before/after
  samples; apply materializes a new staged Parquet via partial-file + fsync +
  `os.replace`, appends to a durable `edits.json` log, and never touches the
  immutable source. `resolve_handle` chains edits so each edit builds on the last.
  Scan-provenance columns (`filename`) are hidden and stripped.
- `api/routes/edits.py`:
  - `POST /api/sessions/{id}/edits/preview` — parse + preview (no data change)
  - `POST /api/sessions/{id}/edits` — requires `approved: true`, else 400
  - `GET /api/sessions/{id}/edits` — applied-edit history
  All routes require the session token.

## Verification

- `backend/tests/editing/test_parser.py`: grammar acceptance and rejection.
- `backend/tests/editing/test_engine.py`: previews (replace/rename/drop/fill),
  apply immutability + atomicity, chained edits, typed errors, edit log.
- `backend/tests/api/test_edits.py`: end-to-end upload → preview → approval
  gating → chained applies → history; error mapping; auth.

## Commit

- `d5b78e9 feat: edit columns and data from typed user commands`
