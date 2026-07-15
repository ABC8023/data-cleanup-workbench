# Task 5 Report: Structured Finding Detectors

## Status

DONE

## Implementation

- Added the `Finding` model (stable id, rule id/version, category, severity,
  affected counts/ratio, evidence, bounded examples, confidence, suggested
  operation, risk level, provenance) and a read-only `Detector` protocol.
- Added `findings/base.py` with `stable_finding_id` (SHA-256 over fingerprint,
  rule id/version, table, columns), `bounded_examples` (DISTINCT, value-ordered,
  capped at 10), and the reusable `SqlDetector` dataclass driven by one documented
  SQL boolean predicate per rule, with an `applies` gate over column profiles.
- Detector catalog:
  - `schema.empty_header` (error, review_required, suggests rename_column)
  - `completeness.null_token` (warning, review_required, suggests replace_value)
  - `validity.mixed_date` (warning, custom detector requiring both ISO and
    slash formats present; evidence records both counts)
  - `validity.numeric_symbol` (warning, currency-prefixed numbers incl. RM/$/€/£)
  - `validity.invalid_email` (warning, informational, gated to email-named columns)
  - `consistency.whitespace` (warning, safe, suggests trim_whitespace)
  - `consistency.case_variant` (warning, review_required, group-by-lower predicate)
  - `statistics.rare_category` (info, informational, no suggestion, gated to
    low-cardinality categorical columns)
- `FindingRegistry.default()` composes the catalog; output is sorted by severity
  desc, affected ratio desc, rule id, then columns, so detector order never
  changes results.
- Scan-provenance columns (`filename`) are now declared once in `ingest/base.py`
  as `SYSTEM_COLUMNS` and skipped by both detectors and the edit engine.

## Verification

- `backend/tests/findings/test_detectors.py`: table-driven rule emission for all
  eight rules, identity/order stability under reversed detector composition,
  ratio reconciliation, bounded sanitized examples, informational rules never
  suggesting operations, JSON round-trips.
- Full backend suite (95 tests), `ruff check`, and `mypy backend/src` all pass.

## Commit

- `5d6e5ca feat: detect structured data quality findings`
