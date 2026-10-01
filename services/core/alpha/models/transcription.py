"""Turns recorded speech into text through Groq Whisper or OpenAI — stdlib multipart over
`urllib`, no new HTTP dependency, mirroring Bridge's own webview-mic -> Whisper flow (same
author; see Bridge's platform/apps/api/src/voice-transcription.ts). Raw audio bytes live only in
memory for the one outbound call: never written to disk, never logged. The provider's key goes
only in the Authorization header, never returned or logged either."""

from __future__ import annotations

import json
import mimetypes
import secrets
import urllib.error
import urllib.request

from alpha.models import keychain

# ~25 MB, matching the providers' own upload limit.
MAX_AUDIO_BYTES = 25 * 1024 * 1024

# Keychain provider id -> (transcription endpoint, model id). Tried in this order unless a
# `preferred` id is given (and has a saved key), in which case it goes first.
_PROVIDERS: tuple[tuple[str, str, str], ...] = (
    ("groq", "https://api.groq.com/openai/v1/audio/transcriptions", "whisper-large-v3-turbo"),
    ("chatgpt_api", "https://api.openai.com/v1/audio/transcriptions", "whisper-1"),
)


class TranscriptionError(Exception):
    """Plain language, safe to show as-is: never carries the key or the raw provider payload."""


class NoProviderAvailable(TranscriptionError):
    pass


def _multipart(model: str, filename: str, content: bytes, content_type: str) -> tuple[bytes, str]:
    boundary = f"----alpha{secrets.token_hex(16)}"
    model_part = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{model}\r\n"
    ).encode()
    file_head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode()
    body = model_part + file_head + content + f"\r\n--{boundary}--\r\n".encode()
    return body, boundary


def _call(url: str, model: str, api_key: str, audio: bytes, mime: str) -> str:
    ext = mimetypes.guess_extension(mime) or ".webm"
    body, boundary = _multipart(model, f"speech{ext}", audio, mime)
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - fixed https hosts
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise TranscriptionError("The saved key was rejected.") from exc
        raise TranscriptionError(
            f"The transcription service returned an error ({exc.code})."
        ) from exc
    except urllib.error.URLError as exc:
        raise TranscriptionError(
            f"Could not reach the transcription service: {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise TranscriptionError("The transcription service took too long to answer.") from exc
    text = result.get("text")
    if not isinstance(text, str):
        raise TranscriptionError("The transcription service returned no text.")
    return text


def transcribe(audio: bytes, mime: str, preferred: str | None = None) -> str:
    """Transcribes `audio` through the first provider with a saved key: `preferred` (a Keychain
    provider id, "groq" or "chatgpt_api") first when given and its key is saved, then Groq, then
    OpenAI. Raises NoProviderAvailable when neither key is saved, TranscriptionError on any
    provider failure."""
    if len(audio) > MAX_AUDIO_BYTES:
        raise TranscriptionError("That recording is too long to transcribe (25 MB limit).")
    order = list(_PROVIDERS)
    if preferred:
        order.sort(key=lambda p: p[0] != preferred)
    for provider_id, url, model in order:
        key = keychain.get_key(provider_id)
        if not key:
            continue
        return _call(url, model, key, audio, mime)
    raise NoProviderAvailable("No transcription key is saved yet. Add one in Settings -> Models.")


def demo() -> None:  # ponytail: smallest runnable self-check, exercised via a fake urlopen
    import unittest.mock as mock

    with mock.patch.object(keychain, "get_key", side_effect=lambda p: "k" if p == "groq" else None):
        with mock.patch(
            "urllib.request.urlopen",
            return_value=mock.MagicMock(
                __enter__=lambda s: mock.MagicMock(read=lambda: b'{"text": "hello"}'),
                __exit__=lambda *a: None,
            ),
        ):
            assert transcribe(b"fake-audio", "audio/webm") == "hello"
    with mock.patch.object(keychain, "get_key", return_value=None):
        try:
            transcribe(b"fake-audio", "audio/webm")
            raise AssertionError("expected NoProviderAvailable")
        except NoProviderAvailable:
            pass
    print("transcription demo: ok")


if __name__ == "__main__":
    demo()
