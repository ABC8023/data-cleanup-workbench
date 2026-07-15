from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from data_workbench.ai.providers import AiProvider, AiProviderError

PREVIEW_TTL = timedelta(minutes=5)


class DictionaryPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    columns: list[dict[str, object]]
    approved_samples: dict[str, list[str]] = Field(default_factory=dict)


class SuggestedColumn(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str


class DictionarySuggestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    columns: list[SuggestedColumn]


class AiPayloadPreview(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    provider: str
    payload: DictionaryPayload
    expires_at: datetime


class AiOptionalError(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str


class AiAttempt(BaseModel):
    model_config = ConfigDict(frozen=True)

    suggestion: DictionarySuggestion | None = None
    fallback: dict[str, Any]
    error: AiOptionalError | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PreviewStore:
    """One-time, expiring storage for approved-payload previews."""

    def __init__(self) -> None:
        self._previews: dict[str, AiPayloadPreview] = {}

    def save(self, preview: AiPayloadPreview) -> None:
        self._previews[preview.id] = preview

    def consume(self, preview_id: str, now: datetime) -> AiPayloadPreview:
        preview = self._previews.pop(preview_id, None)
        if preview is None or now > preview.expires_at:
            raise AiProviderError("expired")
        return preview


def payload_columns(profile: dict[str, Any]) -> list[dict[str, object]]:
    # Schema and aggregate statistics only: raw cell values are excluded
    # unless the user explicitly selected them as approved samples.
    return [
        {
            "name": column["name"],
            "inferred_type": column["inferred_type"],
            "null_count": column["null_count"],
            "distinct_count": column["distinct_count"],
        }
        for column in profile["columns"]
    ]


class AiGateway:
    def __init__(
        self,
        provider: AiProvider,
        store: PreviewStore,
        clock: Callable[[], datetime],
        deterministic_dictionary: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        self.provider = provider
        self.store = store
        self.clock = clock
        self.deterministic_dictionary = deterministic_dictionary

    def preview_dictionary_request(
        self,
        profile: dict[str, Any],
        selected_samples: dict[str, list[str]],
    ) -> AiPayloadPreview:
        payload = DictionaryPayload(
            columns=payload_columns(profile),
            approved_samples=selected_samples,
        )
        preview = AiPayloadPreview(
            id=secrets.token_urlsafe(24),
            provider=self.provider.name,
            payload=payload,
            expires_at=self.clock() + PREVIEW_TTL,
        )
        self.store.save(preview)
        return preview

    def approve(self, preview_id: str) -> DictionarySuggestion:
        preview = self.store.consume(preview_id, now=self.clock())
        raw = self.provider.suggest_dictionary(
            preview.payload.model_dump(mode="json")
        )
        try:
            return DictionarySuggestion.model_validate(raw)
        except ValidationError as error:
            raise AiProviderError("malformed") from error

    def approve_or_fallback(
        self, preview_id: str, profile: dict[str, Any]
    ) -> AiAttempt:
        fallback = self.deterministic_dictionary(profile)
        try:
            return AiAttempt(suggestion=self.approve(preview_id), fallback=fallback)
        except AiProviderError as error:
            return AiAttempt(
                fallback=fallback,
                error=AiOptionalError(
                    code=error.code, message="AI suggestion unavailable"
                ),
            )
