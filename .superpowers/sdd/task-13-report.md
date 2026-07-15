# Task 13 Report: Findings, Preview, Recipe, and Duplicate Review UI

## Status

DONE

## Implementation

- `src/features/issues/suggest.ts`: maps a finding's backend
  `suggested_operation` onto a typed recipe step (parse_date, cast_number,
  replace_value seeded from the finding's own example value, normalize_text
  for trim/case suggestions). Informational findings map to no action.
- `src/features/issues/IssueList.tsx` + `PreviewPanel.tsx`: each finding shows
  severity, confidence, affected count, risk level, columns, and collapsed
  examples. "Review" fetches a preview of the current recipe plus the candidate
  step and renders before/after sample tables, row-count delta, and validation
  failures. Approval is explicit: `review_required` findings additionally
  require a confirmation checkbox before the approve button enables, and
  opening/closing the panel never implies approval.
- `src/features/recipe/RecipeEditor.tsx`: ordered step list with
  keyboard-accessible move up/down/remove buttons; every change flows through
  `onChange` so the app re-previews against the typed recipe.
- `src/features/duplicates/DuplicateReview.tsx`: shows candidate row values,
  per-field evidence percentages, and confidence; radio actions default to
  undecided, and remove/merge require an explicit survivor selection before
  the save button enables.
- `App.tsx`: profiled sessions now render Overview → IssueList → RecipeEditor;
  approved steps accumulate client-side and previews always send the full
  ordered recipe with the session's source fingerprint. Duplicate review is a
  tested standalone component; it wires into the outputs flow in Task 14.
- API client gained `previewRecipe`; types gained recipe, preview, and
  duplicate contracts mirroring the backend.

## Verification

- `npm --prefix frontend test -- --run`: 10 tests passing — approval only
  after preview + confirmation, no review action for informational findings,
  keyboard reordering and removal, undecided-by-default duplicate decisions
  with survivor requirements.
- `npm --prefix frontend run build` and `lint`: clean.
