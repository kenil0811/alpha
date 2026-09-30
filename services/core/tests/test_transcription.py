"""Whisper transcription: provider selection (preferred, then Groq, then OpenAI), the multipart
body shape, and that a saved key never leaks into an error message or log."""

from __future__ import annotations

import json
from typing import Any

import pytest
from alpha.models import transcription


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _keys(**saved: str) -> Any:
    return lambda provider: saved.get(provider)


def test_no_key_saved_raises_no_provider_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transcription.keychain, "get_key", _keys())
    with pytest.raises(transcription.NoProviderAvailable):
        transcription.transcribe(b"audio-bytes", "audio/webm")


def test_uses_groq_first_when_both_keys_are_saved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transcription.keychain, "get_key", _keys(groq="g-key", chatgpt="o-key"))
    seen: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: int = 60) -> FakeResponse:
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        return FakeResponse({"text": "hello world"})

    monkeypatch.setattr(transcription.urllib.request, "urlopen", fake_urlopen)
    text = transcription.transcribe(b"audio-bytes", "audio/webm")
    assert text == "hello world"
    assert "groq" in seen["url"]
    assert seen["auth"] == "Bearer g-key"


def test_preferred_provider_goes_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transcription.keychain, "get_key", _keys(groq="g-key", chatgpt="o-key"))
    seen: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: int = 60) -> FakeResponse:
        seen["url"] = req.full_url
        return FakeResponse({"text": "hi"})

    monkeypatch.setattr(transcription.urllib.request, "urlopen", fake_urlopen)
    transcription.transcribe(b"audio-bytes", "audio/webm", preferred="chatgpt")
    assert "openai.com" in seen["url"]


def test_falls_back_to_openai_when_only_that_key_is_saved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transcription.keychain, "get_key", _keys(chatgpt="o-key"))
    monkeypatch.setattr(
        transcription.urllib.request,
        "urlopen",
        lambda req, timeout=60: FakeResponse({"text": "ok"}),
    )
    assert transcription.transcribe(b"audio-bytes", "audio/webm") == "ok"


def test_rejected_key_message_never_contains_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    monkeypatch.setattr(transcription.keychain, "get_key", _keys(groq="super-secret-key"))

    def fail(req: Any, timeout: int = 60) -> None:
        raise urllib.error.HTTPError(req.full_url, 401, "unauthorized", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(transcription.urllib.request, "urlopen", fail)
    with pytest.raises(transcription.TranscriptionError) as exc:
        transcription.transcribe(b"audio-bytes", "audio/webm")
    assert "super-secret-key" not in str(exc.value)


def test_audio_over_the_size_cap_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transcription.keychain, "get_key", _keys(groq="g-key"))
    with pytest.raises(transcription.TranscriptionError, match="too long"):
        transcription.transcribe(b"0" * (transcription.MAX_AUDIO_BYTES + 1), "audio/webm")


def test_multipart_body_carries_model_and_file_parts() -> None:
    body, boundary = transcription._multipart("whisper-1", "speech.webm", b"RIFF..", "audio/webm")
    text = body.decode("latin-1")
    assert f"--{boundary}" in text
    assert 'name="model"' in text and "whisper-1" in text
    assert 'name="file"; filename="speech.webm"' in text
    assert "Content-Type: audio/webm" in text
    assert text.strip().endswith(f"--{boundary}--")


def test_demo_runs() -> None:
    transcription.demo()
