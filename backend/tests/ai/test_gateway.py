from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from data_workbench.ai.gateway import AiGateway, PreviewStore
from data_workbench.ai.providers import AiProviderError, DisabledProvider

PROFILE: dict[str, Any] = {
    "source_fingerprint": "fixture-sha256",
    "table": "data",
    "row_count": 4,
    "columns": [
        {
            "name": "customer_id",
            "inferred_type": "VARCHAR",
            "null_count": 1,
            "distinct_count": 3,
            "examples": ["c1", "c2"],
        }
    ],
}

DETERMINISTIC_FALLBACK = {"table": "data", "columns": ["customer_id"]}

START = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


class FakeProvider:
    name = "fake"

    def __init__(self, result: Any = None, error: AiProviderError | None = None):
        self.calls: list[dict[str, Any]] = []
        self.result = result
        self.error = error

    def suggest_dictionary(self, payload: dict[str, Any]) -> Any:
        self.calls.append(payload)
        if self.error is not None:
            raise self.error
        return self.result


GOOD_RESULT = {
    "columns": [{"name": "customer_id", "description": "Customer key"}]
}


def make_gateway(provider: Any, clock: FakeClock) -> AiGateway:
    return AiGateway(
        provider,
        PreviewStore(),
        clock=clock,
        deterministic_dictionary=lambda profile: DETERMINISTIC_FALLBACK,
    )


def test_preview_does_not_call_provider_and_approval_sends_exact_payload() -> None:
    provider = FakeProvider(result=GOOD_RESULT)
    gateway = make_gateway(provider, FakeClock())

    preview = gateway.preview_dictionary_request(PROFILE, selected_samples={})

    assert provider.calls == []
    assert preview.provider == "fake"
    assert preview.payload.approved_samples == {}
    assert preview.payload.columns == [
        {
            "name": "customer_id",
            "inferred_type": "VARCHAR",
            "null_count": 1,
            "distinct_count": 3,
        }
    ]

    suggestion = gateway.approve(preview.id)

    assert provider.calls == [preview.payload.model_dump(mode="json")]
    assert suggestion.columns[0].description == "Customer key"


def test_selected_samples_are_the_only_raw_values_sent() -> None:
    provider = FakeProvider(result=GOOD_RESULT)
    gateway = make_gateway(provider, FakeClock())

    preview = gateway.preview_dictionary_request(
        PROFILE, selected_samples={"customer_id": ["c1"]}
    )
    gateway.approve(preview.id)

    sent = provider.calls[0]
    assert sent["approved_samples"] == {"customer_id": ["c1"]}
    assert all("examples" not in column for column in sent["columns"])


def test_previews_are_single_use() -> None:
    gateway = make_gateway(FakeProvider(result=GOOD_RESULT), FakeClock())
    preview = gateway.preview_dictionary_request(PROFILE, selected_samples={})

    gateway.approve(preview.id)
    with pytest.raises(AiProviderError, match="expired"):
        gateway.approve(preview.id)


@pytest.mark.parametrize(
    "mode", ["disabled", "denied", "expired", "timeout", "malformed"]
)
def test_ai_failures_preserve_deterministic_dictionary(mode: str) -> None:
    clock = FakeClock()
    provider: Any
    if mode == "disabled":
        provider = DisabledProvider()
    elif mode == "malformed":
        provider = FakeProvider(result={"nonsense": True})
    elif mode == "expired":
        provider = FakeProvider(result=GOOD_RESULT)
    else:
        provider = FakeProvider(error=AiProviderError(mode))
    gateway = make_gateway(provider, clock)
    preview = gateway.preview_dictionary_request(PROFILE, selected_samples={})
    if mode == "expired":
        clock.now = START + timedelta(minutes=6)

    result = gateway.approve_or_fallback(preview.id, PROFILE)

    assert result.suggestion is None
    assert result.fallback == DETERMINISTIC_FALLBACK
    assert result.error is not None
    assert result.error.code == mode
    assert result.error.message == "AI suggestion unavailable"
