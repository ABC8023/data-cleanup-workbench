from __future__ import annotations

import ipaddress
import logging
import secrets
from typing import Any, Mapping

REDACTED = "[redacted]"
# Keys whose values must never reach logs: raw data samples and credentials.
SENSITIVE_KEY_MARKERS = (
    "sample",
    "example",
    "value",
    "key",
    "token",
    "secret",
    "password",
    "credential",
    "authorization",
)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def validate_loopback_host(host: str) -> str:
    if host.lower() == "localhost":
        return host
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise ValueError(f"host {host!r} is not a loopback address") from error
    if not address.is_loopback:
        raise ValueError(f"host {host!r} is not a loopback address")
    return host


def redact_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        lowered = key.lower()
        if any(marker in lowered for marker in SENSITIVE_KEY_MARKERS):
            redacted[key] = REDACTED
        elif isinstance(value, Mapping):
            redacted[key] = redact_mapping(value)
        else:
            redacted[key] = value
    return redacted


class Redactor:
    """Logs structured error context with sensitive fields removed."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("data_workbench")

    def log_error(self, context: Mapping[str, Any]) -> None:
        self.logger.error("workbench error: %s", redact_mapping(context))
