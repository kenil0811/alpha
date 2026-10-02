"""Settings -> Models: what account or key each provider has, backed by the macOS Keychain, and
a tiny live test per provider. Never returns a saved key to the caller, only its last 4 characters.
"""

from __future__ import annotations

import json
import os
import pwd
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from alpha.models import claude_oauth, keychain
from alpha.models.preferences import Preferences
from alpha.models.providers import ProviderHTTPError, list_models, probe

# A cached live-test result is reused for this long before Core probes the provider again.
STATUS_CACHE_SECONDS = 60.0

# States that mean "nothing to probe" - the dot is grey without spending a network/CLI call.
# provider -> what it said when a real call was refused (e.g. Claude's organization turned off
# subscription access for Claude Code). `auth status` still says "logged in" then, so without
# this the row stayed green while every call failed. Cleared by a call that works, a new
# sign-in or a reconnect.
_REFUSED: dict[str, str] = {}
_REFUSED_LOCK = threading.Lock()

# The model route each sign-in row drives, to name the row a refused route belongs to.
ROUTE_ACCOUNT = {"claude-code-cli": "claude", "chatgpt-codex-cli": "chatgpt"}


def note_refused(provider: str, said: str) -> None:
    with _REFUSED_LOCK:
        _REFUSED[provider] = " ".join(said.split())[:200]


def note_working(provider: str) -> None:
    with _REFUSED_LOCK:
        _REFUSED.pop(provider, None)


def refused(provider: str) -> str | None:
    with _REFUSED_LOCK:
        return _REFUSED.get(provider)


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
# Where to get a sign-in row's CLI when it can't be installed for the person.
INSTALL_PAGES: dict[str, str] = {"chatgpt": "https://github.com/openai/codex"}
# Copies of `codex` that come with the ChatGPT app (not a terminal command until linked).
CODEX_BUNDLES = (
    "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex",
    "~/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex",
)
CODEX_PACKAGE = "@openai/codex"
INSTALL_SECONDS = 300.0
# An unfinished browser sign-in is stopped after this long.
SIGN_IN_SECONDS = 300.0


# Settings -> Models `models.provider` value -> the account row it means (the "default" star).
PROVIDER_PREF_TO_ACCOUNT: dict[str, str] = {
    "claude": "claude",
    "claude_api": "claude_api",
    "chatgpt_codex": "chatgpt",
    "chatgpt_api": "chatgpt_api",
    "openrouter": "openrouter",
    "grok": "grok",
}
# account -> the preference holding its selected model. Claude's is the new-build stage's (the
# per-stage choices stay in Settings; this is the one the model picker shows and sets).
MODEL_PREFERENCE: dict[str, str] = {
    "claude": "models.claude_model",
    "claude_api": "models.claude_model",
    "chatgpt": "models.codex_model",
    "chatgpt_api": "models.chatgpt_model",
    "openrouter": "models.openrouter_model",
    "grok": "models.grok_model",
}
CLAUDE_MODELS = [
    {"id": "opus", "label": "Claude Opus"},
    {"id": "sonnet", "label": "Claude Sonnet"},
    {"id": "haiku", "label": "Claude Haiku"},
]
# ponytail: static, used only when Codex's own models cache (~/.codex/models_cache.json, what
# `codex` lists in its /model picker) can't be read; update when Codex's line-up changes.
CODEX_MODELS = [{"id": "gpt-5.5", "label": "GPT-5.5"}]
MODELS_CACHE_SECONDS = 600.0
# OpenAI's /models lists every model (embeddings, speech, images); keep the chat ones.
_OPENAI_CHAT_PREFIXES = ("gpt-", "o1", "o3", "o4", "chatgpt-")
_OPENAI_NOT_CHAT = ("audio", "realtime", "tts", "transcribe", "image", "embedding", "search")


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
        # A background `npm install` of a CLI, and whether the last one failed.
        self._installs: dict[str, subprocess.Popen[bytes]] = {}
        self._install_failed: set[str] = set()
        # provider -> (monotonic time fetched, its /models list); successes only.
        self._models_cache: dict[str, tuple[float, list[dict[str, str]]]] = {}
        self._lock = threading.Lock()

    def _spec(self, provider: str) -> dict[str, Any]:
        spec = PROVIDERS.get(provider)
        if spec is None:
            raise UnknownProvider(f"there is no provider {provider!r}")
        return spec

    def list_providers(self) -> list[dict[str, Any]]:
        """Every row; `default` marks the one `models.provider` resolves to (Claude when unset)."""
        chosen = self._prefs.get("models.provider") if self._prefs is not None else "claude"
        default = PROVIDER_PREF_TO_ACCOUNT.get(str(chosen), "claude")
        return [{**self._describe(pid), "default": pid == default} for pid in PROVIDERS]

    # ----- models per provider -----------------------------------------------------------

    def models(self, provider: str) -> dict[str, Any]:
        """The models the provider offers and the one selected for it. Never raises for a
        provider that can't be reached: its list is just empty."""
        spec = self._spec(provider)
        if provider in ("claude", "claude_api"):
            listed = CLAUDE_MODELS
        elif provider == "chatgpt":
            listed = self._codex_models() or CODEX_MODELS
        else:
            listed = self._fetched_models(provider, spec["base_url"])
        pref = MODEL_PREFERENCE.get(provider)
        selected = self._prefs.get(pref) if pref and self._prefs is not None else None
        return {"models": listed, "selected": selected if selected not in ("", "default") else None}

    def select_model(self, provider: str, model: str) -> dict[str, Any]:
        """Save the provider's selected model (its MODEL_PREFERENCE)."""
        self._spec(provider)
        pref = MODEL_PREFERENCE.get(provider)
        if pref is None or self._prefs is None:
            raise SignInUnavailable(f"{PROVIDERS[provider]['label']} has no model to choose yet")
        self._prefs.update({pref: model})  # InvalidSetting for a value the setting refuses
        return self.models(provider)

    def _codex_models(self) -> list[dict[str, str]]:
        """The models the Codex CLI itself lists (its cache of what this account may use)."""
        try:
            cache = json.loads(
                (Path(self._env["HOME"]) / ".codex" / "models_cache.json").read_text()
            )
            listed = sorted(
                (m for m in cache.get("models", []) if m.get("visibility") == "list"),
                key=lambda m: m.get("priority", 0),
            )
        except (OSError, ValueError, AttributeError):
            return []
        return [
            {"id": str(m["slug"]), "label": str(m.get("display_name") or m["slug"])}
            for m in listed
            if m.get("slug")
        ]

    def _fetched_models(self, provider: str, base_url: str | None) -> list[dict[str, str]]:
        cached = self._models_cache.get(provider)
        if cached is not None and time.monotonic() - cached[0] < MODELS_CACHE_SECONDS:
            return cached[1]
        key = keychain.get_key(provider)
        if not base_url or (not key and provider != "openrouter"):
            return []
        try:
            raw = list_models(base_url, key, timeout=5)
        except (ProviderHTTPError, OSError, ValueError):
            return []
        if provider == "chatgpt_api":
            raw = [
                m
                for m in raw
                if str(m["id"]).startswith(_OPENAI_CHAT_PREFIXES)
                and not any(word in str(m["id"]) for word in _OPENAI_NOT_CHAT)
            ]
        listed = sorted(
            ({"id": str(m["id"]), "label": str(m.get("name") or m["id"])} for m in raw),
            key=lambda m: m["label"].lower(),
        )
        self._models_cache[provider] = (time.monotonic(), listed)
        return listed

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
        install = self._installs.get(provider)
        return {
            "id": provider,
            "label": spec["label"],
            "state": state,
            "installing": install is not None and install.poll() is None,
            "install_failed": provider in self._install_failed,
            "cli_present": cli_present,
            "signed_in": signed_in,
            "key_last4": saved,
            "dot": self._dot(provider, state),
        }

    def _cached_test(self, provider: str) -> dict[str, Any]:
        """test_connection(), reused for STATUS_CACHE_SECONDS so opening Settings repeatedly
        (or every provider row redrawing) doesn't re-probe a CLI or hit a provider's API."""
        said = refused(provider)
        if said:
            return {
                "ok": False,
                "message": f"Refused: {said} Reconnect to sign in with another account or "
                "organization, or choose another model.",
            }
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
        note_working(provider)
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
        note_working(provider)
        if provider == "claude":
            claude_oauth.open_in_browser(claude_oauth.authorize_url())
            return {**self._describe(provider), "needs_code": True}
        args = SIGN_IN_ARGS.get(provider)
        path = shutil.which(spec["binary"], path=self._env["PATH"]) if spec["binary"] else None
        if args is None:
            raise SignInUnavailable(f"{spec['label']} signs in with a key, not a browser.")
        if path is None:
            raise SignInUnavailable(f"Install {spec['binary'].title()} first.")
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

    def install(self, provider: str) -> dict[str, Any]:
        """Make the provider's CLI a terminal command without showing a terminal: link the copy
        the ChatGPT app ships into ~/.local/bin (instant), else `npm install` it there in the
        background (the row reports `installing` until it lands). Only when neither can work is
        its install page opened in the browser."""
        spec = self._spec(provider)
        if provider != "chatgpt":
            raise SignInUnavailable(f"{spec['label']} has nothing to install.")
        self._status_cache.pop(provider, None)
        self._install_failed.discard(provider)
        if shutil.which("codex", path=self._env["PATH"]):
            return self._describe(provider)
        local = Path(self._env["HOME"]) / ".local"
        bundle = next(
            (p for p in map(os.path.expanduser, CODEX_BUNDLES) if os.access(p, os.X_OK)), None
        )
        if bundle:
            link = local / "bin" / "codex"
            link.parent.mkdir(parents=True, exist_ok=True)
            if link.is_symlink():
                link.unlink()  # a stale link to a moved app
            link.symlink_to(bundle)
            return self._describe(provider)
        npm = shutil.which("npm", path=self._env["PATH"])
        if npm is None:
            claude_oauth.open_in_browser(INSTALL_PAGES[provider])
            raise SignInUnavailable(
                "Codex couldn't be installed here. Its install page is open in your browser; "
                "or paste a key in ChatGPT API."
            )
        with self._lock:
            running = self._installs.get(provider)
            if running is None or running.poll() is not None:
                proc = subprocess.Popen(
                    [npm, "install", "-g", "--prefix", str(local), CODEX_PACKAGE],
                    env=self._env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                self._installs[provider] = proc
                threading.Thread(
                    target=self._watch_install, args=(provider, proc), daemon=True
                ).start()
        return self._describe(provider)

    def _watch_install(self, provider: str, proc: subprocess.Popen[bytes]) -> None:
        try:
            code = proc.wait(timeout=INSTALL_SECONDS)
        except subprocess.TimeoutExpired:
            proc.kill()
            code = -1
        if code != 0:
            self._install_failed.add(provider)
        self._status_cache.pop(provider, None)

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
