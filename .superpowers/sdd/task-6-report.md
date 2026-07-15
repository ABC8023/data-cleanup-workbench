# Task 6 Report: Background Jobs, Progress, and Cancellation

## Status

DONE

## Implementation

- `jobs/manager.py`: `JobManager` with a heavy-job semaphore (app default 1),
  per-job bounded append-only event deques (500), monotonic event sequences,
  cooperative cancellation via `JobContext.raise_if_cancelled()`, and terminal
  states `succeeded`/`failed`/`cancelled`. Raw exceptions are never exposed:
  unexpected failures map to `job_failed`, and work can raise `JobFailure(code)`
  for sanitized typed codes (`invalid_input` for malformed/unsupported sources).
- `api/dependencies.py`: frozen `Services` container (sessions, adapters,
  duckdb, profiler, findings, jobs) wired in `create_app` and shared via
  `app.state.services`.
- `api/routes/jobs.py`: `GET /api/jobs/{id}` (status + sanitized error code),
  `GET /api/jobs/{id}/events` (SSE stream of `JobEvent` JSON), and
  `DELETE /api/jobs/{id}` (202, cooperative cancel). Unknown jobs are 404.
- `api/routes/sessions.py`: `POST /api/sessions/{id}/profile` (202 + job id)
  runs the blocking inspect → profile → findings → persist pipeline via
  `asyncio.to_thread`, publishing stages `inspect`/`profile`/`findings`/`persist`
  and checking cancellation between profiler columns. `GET
  /api/sessions/{id}/profile` returns the persisted profile + findings.
- `storage/session_repository.py`: `save_profile` durably (tmp + fsync +
  write-through replace) writes `profile.json`, `findings.json`, and republishes
  `session.json` with state `profiled`; `load_profile` reads them back.
- `ingest/registry.py`: added `inspect_declared(source, declared_filename,
  session_dir)` so staged `source.bin` files resolve adapters from the declared
  upload filename; the edit routes were refactored onto it.

## Verification

- `backend/tests/jobs/test_manager.py`: cancellation, ordered event streams,
  sanitized failure codes, single-flight heavy-job gating, unknown-job errors.
- `backend/tests/api/test_profile_jobs.py`: end-to-end upload → profile job →
  persisted profile/findings + `profiled` session state; SSE stage ordering;
  malformed input failing with `invalid_input` and no persisted profile;
  cancel + retry; unknown-id and auth rejections.
- Full backend suite (105 tests), `ruff check`, and `mypy backend/src` pass.

## Notes

- API tests must hold one `TestClient` open across requests (`with TestClient`) —
  otherwise each request runs on a throwaway event loop and background jobs are
  cancelled when it closes.
