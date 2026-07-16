from __future__ import annotations

import json
import os
from typing import Any, Protocol

import httpx

KEYRING_SERVICE = "data-cleanup-workbench"
KEYRING_API_KEY = "ai_api_key"
REQUEST_TIMEOUT_SECONDS = 10.0
ANTHROPIC_MODEL = "claude-opus-4-8"
ANTHROPIC_TIMEOUT_SECONDS = 60.0
ANTHROPIC_MAX_TOKENS = 2048

DICTIONARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "columns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["name", "description"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["columns"],
    "additionalProperties": False,
}

DICTIONARY_PROMPT = (
    "You are documenting a tabular dataset. For each column in the metadata"
    " below, write one plain-English sentence describing what the column"
    " likely contains, based on its name, inferred type, and statistics"
    " (and sample values, when present).\n\n"
    "Respond with a JSON object of exactly this shape, covering every column"
    " exactly once and using the exact column names given:\n"
    '{"columns": [{"name": "<column name>", "description": "<one sentence>"}]}'
    "\n\nColumn metadata (JSON):\n"
)


class AiProviderError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AiProvider(Protocol):
    @property
    def name(self) -> str: ...

    def suggest_dictionary(self, payload: dict[str, Any]) -> Any: ...


class DisabledProvider:
    name = "disabled"

    def suggest_dictionary(self, payload: dict[str, Any]) -> Any:
        del payload
        raise AiProviderError("disabled")


def _keyring_api_key() -> str | None:
    import keyring

    key = keyring.get_password(KEYRING_SERVICE, KEYRING_API_KEY)
    return key if key else None


class HttpDictionaryProvider:
    """Posts an approved payload to a configured HTTPS endpoint.

    Credentials come from the OS keyring, never from configuration files, and
    the payload sent is exactly the previewed payload.
    """

    name = "http"

    def __init__(self, url: str) -> None:
        self.url = url

    def suggest_dictionary(self, payload: dict[str, Any]) -> Any:
        headers = {}
        api_key = _keyring_api_key()
        if api_key is not None:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            response = httpx.post(
                self.url,
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException as error:
            raise AiProviderError("timeout") from error
        except httpx.HTTPError as error:
            raise AiProviderError("unavailable") from error
        if response.status_code in {401, 403}:
            raise AiProviderError("denied")
        if response.status_code != 200:
            raise AiProviderError("unavailable")
        try:
            return response.json()
        except ValueError as error:
            raise AiProviderError("malformed") from error


def _extract_json(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        raise AiProviderError("malformed")
    try:
        return json.loads(stripped[start : end + 1])
    except ValueError as error:
        raise AiProviderError("malformed") from error


class AnthropicDictionaryProvider:
    """Drafts column descriptions with Claude via the official Anthropic SDK.

    The API key comes from the OS keyring (service ``data-cleanup-workbench``,
    entry ``ai_api_key``) or the ``ANTHROPIC_API_KEY`` environment variable —
    never from configuration files. Only the previewed, user-approved payload
    (schema plus explicitly approved samples) is sent.
    """

    name = "anthropic"

    def __init__(self, model: str = ANTHROPIC_MODEL) -> None:
        self.model = model

    def _api_key(self) -> str:
        key = _keyring_api_key() or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise AiProviderError("no_api_key")
        return key

    def suggest_dictionary(self, payload: dict[str, Any]) -> Any:
        import anthropic

        client = anthropic.Anthropic(
            api_key=self._api_key(), timeout=ANTHROPIC_TIMEOUT_SECONDS
        )
        prompt = DICTIONARY_PROMPT + json.dumps(payload, indent=2)
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=ANTHROPIC_MAX_TOKENS,
                output_config={
                    "format": {"type": "json_schema", "schema": DICTIONARY_SCHEMA}
                },
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.AuthenticationError as error:
            raise AiProviderError("denied") from error
        except anthropic.PermissionDeniedError as error:
            raise AiProviderError("denied") from error
        except anthropic.APITimeoutError as error:
            raise AiProviderError("timeout") from error
        except anthropic.APIConnectionError as error:
            raise AiProviderError("unavailable") from error
        except anthropic.APIStatusError as error:
            raise AiProviderError("unavailable") from error
        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        return _extract_json(text)
