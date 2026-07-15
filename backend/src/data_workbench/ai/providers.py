from __future__ import annotations

from typing import Any, Protocol

import httpx

KEYRING_SERVICE = "data-cleanup-workbench"
KEYRING_API_KEY = "ai_api_key"
REQUEST_TIMEOUT_SECONDS = 10.0


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
