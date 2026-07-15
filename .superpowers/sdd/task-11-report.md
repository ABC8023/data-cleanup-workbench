# Task 11 Report: Optional AI Privacy Gateway

## Status

DONE

## Implementation

- `ai/providers.py`: `AiProviderError(code)`, `AiProvider` protocol,
  `DisabledProvider` (default — every call fails with code `disabled`), and
  `HttpDictionaryProvider` (posts the exact approved payload to a configured
  URL; API key comes from the OS keyring, never config files; httpx timeouts
  map to `timeout`, 401/403 to `denied`, other transport/status errors to
  `unavailable`, bad JSON to `malformed`).
- `ai/gateway.py`: two-phase consent flow. `preview_dictionary_request`
  builds a `DictionaryPayload` of schema and aggregate statistics only — raw
  cell values are excluded unless the user explicitly selected them as
  approved samples — and stores an `AiPayloadPreview` with a
  cryptographically random id and a five-minute expiry. **No provider request
  occurs during preview.** `approve` consumes the preview one-time (reuse or
  expiry → `expired`), sends exactly the previewed payload, and validates the
  response with Pydantic (`malformed` on mismatch). `approve_or_fallback`
  always returns the deterministic dictionary fallback with a typed
  `AiOptionalError`, so AI failure never blocks deterministic operation.
- API (`api/routes/ai.py`): `POST /api/sessions/{id}/ai/dictionary/preview`
  and `POST .../approve`, requiring a profiled session (409 otherwise). The
  gateway wires into the app with `DisabledProvider` unless
  `AppConfig.ai_provider_url` is set; the deterministic fallback reuses the
  Task 10 dictionary builder.

## Verification

- `backend/tests/ai/test_gateway.py`: preview never calls the provider and
  approval sends the exact previewed payload; selected samples are the only
  raw values transmitted; previews are single-use; parametrized
  disabled/denied/expired/timeout/malformed failures all preserve the
  deterministic fallback with the right error code.
- `backend/tests/api/test_ai_routes.py`: end-to-end two-phase flow against a
  profiled session with the default disabled provider; 409 before profiling,
  404 for unknown sessions, 401 without token.
- Full backend suite (154 tests), `ruff check`, `mypy backend/src` all pass.
