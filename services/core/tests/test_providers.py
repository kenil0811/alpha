"""OpenAI-compatible HTTP calls (OpenAI, OpenRouter, xAI Grok), mocked at urlopen — no network."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from typing import Any

import pytest
from alpha.models.providers import ProviderHTTPError, chat_structured, probe


class _FakeResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = json.dumps(body).encode()

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_probe_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: _FakeResponse({"data": []}))
    probe("https://api.openai.com/v1", "sk-test")  # no exception


def test_probe_bad_key_raises_a_plain_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_401(req: Any, timeout: int) -> None:
        raise urllib.error.HTTPError(req.full_url, 401, "unauthorized", {}, io.BytesIO(b"nope"))

    monkeypatch.setattr(urllib.request, "urlopen", raise_401)
    with pytest.raises(ProviderHTTPError, match="rejected"):
        probe("https://api.openai.com/v1", "sk-bad")


def test_probe_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_url_error(req: Any, timeout: int) -> None:
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(urllib.request, "urlopen", raise_url_error)
    with pytest.raises(ProviderHTTPError, match="Could not reach"):
        probe("https://api.x.ai/v1", "key")


def test_chat_structured_parses_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {
        "choices": [{"message": {"content": json.dumps({"answer": "42"})}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3},
    }
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: _FakeResponse(body))
    output, usage, elapsed = chat_structured(
        "https://openrouter.ai/api/v1",
        "key",
        "openai/gpt-4o-mini",
        "system",
        "prompt",
        {"type": "object", "properties": {"answer": {"type": "string"}}},
    )
    assert output == {"answer": "42"}
    assert usage.input_tokens == 10
    assert usage.output_tokens == 3
    assert elapsed >= 0


def test_chat_structured_rejects_non_json_content(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"choices": [{"message": {"content": "not json"}}]}
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: _FakeResponse(body))
    with pytest.raises(ProviderHTTPError, match="not valid JSON"):
        chat_structured("https://api.x.ai/v1", "key", "grok-4", "s", "p", {"type": "object"})


def test_chat_structured_rejects_no_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    empty = _FakeResponse({"choices": []})
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: empty)
    with pytest.raises(ProviderHTTPError, match="no answer"):
        chat_structured("https://api.x.ai/v1", "key", "grok-4", "s", "p", {"type": "object"})
