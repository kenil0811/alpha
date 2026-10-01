"""Settings -> Models: what account or key each provider has, backed by the macOS Keychain, and
a tiny live test per provider. Never returns a saved key to the caller, only its last 4 characters.
"""

from __future__ import annotations

import os
import pwd
import shutil
import subprocess
import threading
import time
from typing import Any

from alpha.models import claude_oauth, keychain
from alpha.models.preferences import Preferences
from alpha.models.providers import ProviderHTTPError, probe

# A cached live-test result is reused for this long before Core probes the provider again.
STATUS_CACHE_SECONDS = 60.0

# States that mean "nothing to probe" - the dot is grey without spending a network/CLI call.
_NOT_CONNECTED_STATES = {"needs_sign_in", "needs_key", "cli_missing", "not_configured"}

PROVIDER_STATE_LABEL: dict[str, str] = {
    "needs_sign_in": "Not signed in",
    "needs_key": "No key saved",
    "cli_missing": "The command-line tool isn't installed",
    "not_configured": "Not connected",
}

# provider id -> label, cli binary (or None), base url for a key-based test (or None)
PROVIDERS: dict[str, dict[str, Any]] = {
    "claude": {"label": "Claude", "binary": "claude", "base_url": None},
    "claude_api": {"label": "Claude API", "binary": None, "base_url": "https://api.anthropic.com/v1"},
    "chatgpt": {"label": "ChatGPT", "binary": "codex", "base_url": None},
    "chatgpt_api": {"label": "ChatGPT API", "binary": None, "base_url": "https://api.openai.com/v1"},
    "openrouter": {"label": "OpenRouter", "binary": None, "base_url": "https://openrouter.ai/api/v1"},
    "grok": {"label": "Grok", "binary": None, "base_url": "https://api.x.ai/v1"},
    "groq": {"label": "Groq", "binary": None, "base_url": "https://api.groq.com/openai/v1"},
}


# provider -> the CLI arguments that sign in through the browser. The CLI opens the page and
# finishes through its own localhost callback, so nothing here sees a credential. Claude signs
# in through Alpha itself instead (claude_oauth: the browser page, then a pasted code).
SIGN_IN_ARGS: dict[str, list[str]] = {
    "chatgpt": ["login"],
}
# An unfinished browser sign-in is stopped after this long.
SIGN_IN_SECONDS = 300.0


class UnknownProvider(Exception):
    pass


class SignInUnavailable(Exception):
    pass


class ModelAccounts:
    def __init__(
        self,
        preferences: Preferences | None = None,
        tool_path: str | None = None,
        home: str | None = None,
    ) -> None:
        self._prefs = preferences
        # The same PATH and HOME the model calls run the CLIs with (Core's own env is cleared),
        # so "installed" and "signed in" here mean what they mean for a real call.
        self._env = {
            "PATH": tool_path or os.environ.get("PATH", os.defpath),
            "HOME": home or pwd.getpwuid(os.getuid()).pw_dir,
        }
        # provider -> (monotonic time it was probed, the test_connection result)
        self._status_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._sign_ins: dict[str, subprocess.Popen[bytes]] = {}
        self._lock = threading.Lock()

    def _spec(self, provider: str) -> dict[str, Any]:
        spec = PROVIDERS.get(provider)
        if spec is None:
            raise UnknownProvider(f"there is no provider {provider!r}")
        return spec

    def list_providers(self) -> list[dict[str, Any]]:
        return [self._describe(pid) for pid in PROVIDERS]

    def _cli_signed_in(self, provider: str, binary: str) -> bool | None:
        """True/False when the CLI can say so, None when the CLI isn't installed or the check
        itself failed (unknown, not "signed out"). Best-effort: relies on each CLI's own status
        subcommand and plain-text output, not a stable machine-readable contract."""
        if not shutil.which(binary, path=self._env["PATH"]):
            return None
        argv = [binary, "auth", "status"] if provider == "claude" else [binary, "login", "status"]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=5, env=self._env)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return False
        text = (proc.stdout + proc.stderr).lower()
        return "logged in" in text or "authenticated" in text or "logged into" in text

    def _signed_in(self, provider: str, binary: str) -> bool | None:
        if provider == "claude" and claude_oauth.signed_in():
            return True
        return self._cli_signed_in(provider, binary)

    def _describe(self, provider: str) -> dict[str, Any]:
        spec = self._spec(provider)
        saved = keychain.last4(provider)
        binary = spec["binary"]
        cli_present = shutil.which(binary, path=self._env["PATH"]) is not None if binary else None
        signed_in = self._signed_in(provider, binary) if binary else None
        if binary:  # a CLI sign-in row (Claude, ChatGPT); its API key is a row of its own
            missing = "cli_missing" if not cli_present else "needs_sign_in"
            state = "connected" if signed_in and cli_present else missing
        else:
            state = "key_saved" if saved else "not_configured"
        return {
            "id": provider,
            "label": spec["label"],
            "state": state,
            "cli_present": cli_present,
            "signed_in": signed_in,
            "key_last4": saved,
            "dot": self._dot(provider, state),
        }

    def _cached_test(self, provider: str) -> dict[str, Any]:
        """test_connection(), reused for STATUS_CACHE_SECONDS so opening Settings repeatedly
        (or every provider row redrawing) doesn't re-probe a CLI or hit a provider's API."""
        now = time.monotonic()
        cached = self._status_cache.get(provider)
        if cached is not None and now - cached[0] < STATUS_CACHE_SECONDS:
            return cached[1]
        result = self.test_connection(provider)
        self._status_cache[provider] = (now, result)
        return result

    def _dot(self, provider: str, state: str) -> dict[str, str]:
        """Settings -> Models row: grey (nothing to connect yet), green (a live probe just
        succeeded) or red (a live probe just failed - e.g. a rejected key). Grey skips the probe
        entirely; green/red come from the cached live test."""
        if state in _NOT_CONNECTED_STATES:
            return {"color": "grey", "tooltip": PROVIDER_STATE_LABEL.get(state, "Not connected")}
        result = self._cached_test(provider)
        return {"color": "green" if result["ok"] else "red", "tooltip": result["message"]}

    def save_key(self, provider: str, key: str) -> dict[str, Any]:
        self._spec(provider)
        keychain.set_key(provider, key)
        self._status_cache.pop(provider, None)
        return self._describe(provider)

    def remove_key(self, provider: str) -> dict[str, Any]:
        self._spec(provider)
        keychain.delete_key(provider)
        self._status_cache.pop(provider, None)
        return self._describe(provider)

    def reconnect(self, provider: str) -> dict[str, Any]:
        """Disconnect, so the caller can connect again: a key row loses its saved key, Claude
        loses the sign-in Alpha holds, ChatGPT is signed out of `codex`. The UI then starts the
        sign-in (or asks for a key) straight away."""
        spec = self._spec(provider)
        self._status_cache.pop(provider, None)
        if spec["base_url"] is not None and keychain.last4(provider):
            keychain.delete_key(provider)
        if provider == "claude":
            claude_oauth.sign_out()
        path = shutil.which(spec["binary"], path=self._env["PATH"]) if spec["binary"] else None
        if provider == "chatgpt" and path:
            try:
                subprocess.run(
                    [path, "logout"], env=self._env, capture_output=True, timeout=10, check=False
                )
            except (OSError, subprocess.TimeoutExpired):
                pass  # the sign-in that follows still replaces it
        return self._describe(provider)

    def sign_in(self, provider: str) -> dict[str, Any]:
        """Start the provider CLI's own browser sign-in (`claude auth login`, `codex login`).
        A second call while one is still open is a no-op; an unfinished one is stopped after
        SIGN_IN_SECONDS. The caller polls list_providers() to see it land."""
        spec = self._spec(provider)
        self._status_cache.pop(provider, None)
        if provider == "claude":
            claude_oauth.open_in_browser(claude_oauth.authorize_url())
            return {**self._describe(provider), "needs_code": True}
        args = SIGN_IN_ARGS.get(provider)
        path = shutil.which(spec["binary"], path=self._env["PATH"]) if spec["binary"] else None
        if args is None:
            raise SignInUnavailable(f"{spec['label']} signs in with a key, not a browser.")
        if path is None:
            raise SignInUnavailable(f"The `{spec['binary']}` command isn't installed on this Mac.")
        with self._lock:
            running = self._sign_ins.get(provider)
            if running is None or running.poll() is not None:
                proc = subprocess.Popen(
                    [path, *args],
                    env=self._env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                self._sign_ins[provider] = proc
                timer = threading.Timer(SIGN_IN_SECONDS, _stop, args=(proc,))
                timer.daemon = True
                timer.start()
        self._status_cache.pop(provider, None)
        return self._describe(provider)

    def finish_sign_in(self, provider: str, code: str) -> dict[str, Any]:
        """Claude only: the code the sign-in page showed, exchanged for tokens (Keychain)."""
        self._spec(provider)
        if provider != "claude":
            raise SignInUnavailable("Only Claude signs in with a pasted code.")
        try:
            claude_oauth.finish(code)
        except claude_oauth.OAuthError as exc:
            raise SignInUnavailable(str(exc)) from exc
        self._status_cache.pop(provider, None)
        return self._describe(provider)

    def test_connection(self, provider: str) -> dict[str, Any]:
        spec = self._spec(provider)
        key = keychain.get_key(provider)
        if not key and spec["binary"]:
            signed_in = self._signed_in(provider, spec["binary"])
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
            headers = (
                {"x-api-key": key, "anthropic-version": "2023-06-01"}
                if provider == "claude_api"
                else None
            )
            probe(spec["base_url"], key, headers=headers)
        except ProviderHTTPError as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, "message": "Connected."}


def _stop(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is None:
        proc.terminate()


def demo() -> None:  # ponytail: smallest runnable self-check
    accounts = ModelAccounts()
    labels = {p["id"] for p in accounts.list_providers()}
    assert labels == set(PROVIDERS)
    valid_states = {
        "connected", "needs_sign_in", "needs_key", "cli_missing", "key_saved", "not_configured",
    }  # fmt: skip
    for p in accounts.list_providers():
        assert p["state"] in valid_states
        assert p["dot"]["color"] in {"green", "grey", "red"}
    reconnected = accounts.reconnect("openrouter")
    assert reconnected["dot"]["color"] == "grey"
    try:
        accounts.sign_in("openrouter")
        raise AssertionError("expected SignInUnavailable")
    except SignInUnavailable:
        pass
    try:
        accounts.save_key("nope", "x")
        raise AssertionError("expected UnknownProvider")
    except UnknownProvider:
        pass
    print("accounts demo: ok")


if __name__ == "__main__":
    demo()
