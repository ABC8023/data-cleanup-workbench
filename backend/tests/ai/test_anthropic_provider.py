from __future__ import annotations

from typing import Any

import anthropic
import pytest

from data_workbench.ai import providers
from data_workbench.ai.providers import AiProviderError, AnthropicDictionaryProvider

SUGGESTION = '{"columns": [{"name": "city", "description": "Customer city."}]}'


class _TextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _Response:
    def __init__(self, text: str) -> None:
        self.content = [_TextBlock(text)]


class _Messages:
    def __init__(self, text: str, calls: list[dict[str, Any]]) -> None:
        self._text = text
        self._calls = calls

    def create(self, **kwargs: Any) -> _Response:
        self._calls.append(kwargs)
        return _Response(self._text)


def _stub_client(
    monkeypatch: pytest.MonkeyPatch, text: str
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    class _Client:
        def __init__(self, **kwargs: Any) -> None:
            self.messages = _Messages(text, calls)

    monkeypatch.setattr(anthropic, "Anthropic", _Client)
    monkeypatch.setattr(providers, "_keyring_api_key", lambda: "test-key")
    return calls


def test_suggests_dictionary_from_model_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _stub_client(monkeypatch, SUGGESTION)

    result = AnthropicDictionaryProvider().suggest_dictionary(
        {"columns": [{"name": "city"}], "approved_samples": {}}
    )

    assert result == {
        "columns": [{"name": "city", "description": "Customer city."}]
    }
    assert calls[0]["model"] == providers.ANTHROPIC_MODEL
    assert "city" in calls[0]["messages"][0]["content"]


def test_tolerates_markdown_fences(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_client(monkeypatch, f"```json\n{SUGGESTION}\n```")

    result = AnthropicDictionaryProvider().suggest_dictionary({"columns": []})

    assert result["columns"][0]["name"] == "city"


def test_non_json_reply_is_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_client(monkeypatch, "I could not produce JSON, sorry.")

    with pytest.raises(AiProviderError) as excinfo:
        AnthropicDictionaryProvider().suggest_dictionary({"columns": []})

    assert excinfo.value.code == "malformed"


def test_missing_api_key_reports_clear_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(providers, "_keyring_api_key", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(AiProviderError) as excinfo:
        AnthropicDictionaryProvider().suggest_dictionary({"columns": []})

    assert excinfo.value.code == "no_api_key"
