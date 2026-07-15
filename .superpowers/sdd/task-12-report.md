# Task 12 Report: Frontend Shell, Upload, Progress, and Overview

## Status

DONE

## Implementation

- Scaffolded `frontend/` with `npm create vite@8.1.0` (react-ts template) on
  Node 24 / npm 11; installed react 19.2.7, react-dom 19.2.7,
  @tanstack/react-query, zod, and dev tooling (vitest 4, Testing Library,
  jest-dom, user-event, jsdom). `frontend/package-lock.json` is committed.
  Playwright is deferred to Task 15 (E2E) to avoid pulling browser binaries
  before they are needed.
- `src/api/types.ts`: session, profile, finding, and job contracts mirroring
  the backend API.
- `src/api/client.ts`: `ApiClient(baseUrl, token)` — uploads via
  `XMLHttpRequest` with `X-Session-Token`, streaming the `File` as the request
  body (never `FileReader`) with upload progress; JSON `fetch` helpers for
  start-profile, job status, cancel, and saved profile, with a typed
  `ApiError`. The scaffold's `erasableSyntaxOnly` tsconfig forbids constructor
  parameter properties, so fields are declared explicitly.
- `src/features/upload/UploadPanel.tsx`: labeled file input (accepts the five
  supported formats), disabled action until a file is chosen, accessible
  progress bar, `role="alert"` errors.
- `src/features/overview/Overview.tsx`: rows/columns/finding summary and a
  semantic column table; sample values collapsed by default in `<details>`.
- `src/app/App.tsx`: upload → start profile job → poll → overview flow with
  accessible cancel (DELETE job), retry, and failure states. Token comes from
  the `?token=` query parameter; base URL is same-origin for the static mount.
- Vitest configured in `vite.config.ts` (jsdom + jest-dom setup).

## Verification

- `npm --prefix frontend test -- --run`: 4 tests passing (upload flow with
  staged-session callback, disabled-until-chosen + error alert, overview
  summary/table semantics, collapsed samples).
- `npm --prefix frontend run build`: tsc + vite build clean.
- `npm --prefix frontend run lint`: eslint clean.
- Backend suite untouched (154 tests still passing as of Task 11).
