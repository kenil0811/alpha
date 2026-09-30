"""Settings -> Models: what account or key each provider has, backed by the macOS Keychain, and
a tiny live test per provider. Never returns a saved key to the caller, only its last 4 characters.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any

from alpha.models import keychain
from alpha.models.preferences import Preferences
from alpha.models.providers import ProviderHTTPError, probe

# provider id -> label, cli binary (or None), base url for a key-based test (or None)
PROVIDERS: dict[str, dict[str, Any]] = {
    "claude": {"label": "Claude", "binary": "claude", "base_url": None},
    "chatgpt": {"label": "ChatGPT", "binary": "codex", "base_url": "https://api.openai.com/v1"},
    "openrouter": {"label": "OpenRouter", "binary": None, "base_url": "https://openrouter.ai/api/v1"},
    "grok": {"label": "Grok", "binary": None, "base_url": "https://api.x.ai/v1"},
    "groq": {"label": "Groq", "binary": None, "base_url": "https://api.groq.com/openai/v1"},
}


class UnknownProvider(Exception):
    pass


class ModelAccounts:
    def __init__(self, preferences: Preferences | None = None) -> None:
        self._prefs = preferences

    def _spec(self, provider: str) -> dict[str, Any]:
        spec = PROVIDERS.get(provider)
        if spec is None:
            raise UnknownProvider(f"there is no provider {provider!r}")
        return spec

    def list_providers(self) -> list[dict[str, Any]]:
        return [self._describe(pid) for pid in PROVIDERS]

    def _auth_mode(self) -> str:
        return str(self._prefs.get("models.claude_auth_mode")) if self._prefs else "console"

    def _cli_signed_in(self, provider: str, binary: str) -> bool | None:
        """True/False when the CLI can say so, None when the CLI isn't installed or the check
        itself failed (unknown, not "signed out"). Best-effort: relies on each CLI's own status
        subcommand and plain-text output, not a stable machine-readable contract."""
        if not shutil.which(binary):
            return None
        argv = [binary, "auth", "status"] if provider == "claude" else [binary, "login", "status"]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return False
        text = (proc.stdout + proc.stderr).lower()
        return "logged in" in text or "authenticated" in text or "logged into" in text

    def _describe(self, provider: str) -> dict[str, Any]:
        spec = self._spec(provider)
        saved = keychain.last4(provider)
        cli_present = shutil.which(spec["binary"]) is not None if spec["binary"] else None
        signed_in = self._cli_signed_in(provider, spec["binary"]) if spec["binary"] else None
        if provider == "claude":
            state = ("key_saved" if saved else "needs_key") if self._auth_mode() == "api_key" else (
                "connected" if signed_in else "cli_missing" if not cli_present else "needs_sign_in"
            )
        elif provider == "chatgpt":
            state = "key_saved" if saved else "connected" if signed_in else "needs_sign_in"
        else:
            state = "key_saved" if saved else "not_configured"
        return {
            "id": provider,
            "label": spec["label"],
            "state": state,
            "cli_present": cli_present,
            "signed_in": signed_in,
            "key_last4": saved,
        }

    def save_key(self, provider: str, key: str) -> dict[str, Any]:
        self._spec(provider)
        keychain.set_key(provider, key)
        return self._describe(provider)

    def remove_key(self, provider: str) -> dict[str, Any]:
        self._spec(provider)
        keychain.delete_key(provider)
        return self._describe(provider)

    def test_connection(self, provider: str) -> dict[str, Any]:
        spec = self._spec(provider)
        key = keychain.get_key(provider)
        if not key and spec["binary"]:
            signed_in = self._cli_signed_in(provider, spec["binary"])
            if signed_in:
                return {"ok": True, "message": f"Signed in with {spec['label']}."}
            if signed_in is False:
                binary = spec["binary"]
                return {"ok": False, "message": f"Not signed in yet. Run `{binary}` and sign in."}
            binary = spec["binary"]
            return {"ok": False, "message": f"The `{binary}` command isn't installed on this Mac."}
        if not key:
            return {"ok": False, "message": "No key saved yet."}
        if not spec["base_url"]:
            return {"ok": False, "message": "Nothing to test for this provider yet."}
        try:
            probe(spec["base_url"], key)
        except ProviderHTTPError as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, "message": "Connected."}


def demo() -> None:  # ponytail: smallest runnable self-check
    accounts = ModelAccounts()
    labels = {p["id"] for p in accounts.list_providers()}
    assert labels == set(PROVIDERS)
    valid_states = {
        "connected", "needs_sign_in", "needs_key", "cli_missing", "key_saved", "not_configured",
    }  # fmt: skip
    for p in accounts.list_providers():
        assert p["state"] in valid_states
    try:
        accounts.save_key("nope", "x")
        raise AssertionError("expected UnknownProvider")
    except UnknownProvider:
        pass
    print("accounts demo: ok")


if __name__ == "__main__":
    demo()
