"""Settings -> Models account state: keychain-backed, a fake `security` on PATH, no CLI needed
for the key-only providers (OpenRouter, Grok)."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from alpha.models.accounts import ModelAccounts, UnknownProvider
from alpha.models.preferences import Preferences
from alpha.models.providers import ProviderHTTPError
from alpha.storage.control_store import ControlStore


@pytest.fixture(autouse=True)
def fake_security(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    script = tmp_path / "security"
    script.write_text(
        "#!/bin/sh\n"
        f'STORE_DIR="{store_dir}"\n'
        'if [ "$1" = "-i" ]; then\n'
        "  read -r line\n"
        "  svc=$(echo \"$line\" | sed -n 's/.*-s \"\\([^\"]*\\)\".*/\\1/p')\n"
        "  val=$(echo \"$line\" | sed -n 's/.*-w \"\\(.*\\)\"$/\\1/p')\n"
        '  printf "%s" "$val" > "$STORE_DIR/$svc"\n'
        'elif [ "$1" = "find-generic-password" ]; then\n'
        '  [ -f "$STORE_DIR/$3" ] && cat "$STORE_DIR/$3" || exit 44\n'
        'elif [ "$1" = "delete-generic-password" ]; then\n'
        '  rm -f "$STORE_DIR/$3"\n'
        "fi\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    # The fake `security` plus the bare minimum of real shell tools (/bin, /usr/bin: sh, sed,
    # cat) but neither the real PATH nor a real `claude`/`codex`, so a dev machine that happens
    # to have either signed in doesn't change what these tests see.
    monkeypatch.setenv("PATH", f"{tmp_path}:/bin:/usr/bin")


def test_lists_all_providers() -> None:
    ids = {p["id"] for p in ModelAccounts().list_providers()}
    assert ids == {"claude", "chatgpt", "openrouter", "grok", "groq"}


def test_claude_defaults_to_console_and_needs_sign_in_without_the_cli() -> None:
    described = next(p for p in ModelAccounts().list_providers() if p["id"] == "claude")
    assert described["state"] == "cli_missing"  # no `claude` on PATH in this test


def test_claude_in_api_key_mode_reports_needs_key_then_key_saved(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    prefs = Preferences(store)
    prefs.update({"models.claude_auth_mode": "api_key"})
    accounts = ModelAccounts(prefs)
    assert next(p for p in accounts.list_providers() if p["id"] == "claude")["state"] == "needs_key"
    accounts.save_key("claude", "sk-ant-test")
    assert next(p for p in accounts.list_providers() if p["id"] == "claude")["state"] == "key_saved"


def test_openrouter_starts_not_configured_then_key_saved_with_last4() -> None:
    accounts = ModelAccounts()
    openrouter = next(p for p in accounts.list_providers() if p["id"] == "openrouter")
    assert openrouter["state"] == "not_configured"
    accounts.save_key("openrouter", "sk-or-abcd1234")
    described = next(p for p in accounts.list_providers() if p["id"] == "openrouter")
    assert described["state"] == "key_saved"
    assert described["key_last4"] == "1234"


def test_remove_key_reverts_state() -> None:
    accounts = ModelAccounts()
    accounts.save_key("grok", "xai-key-123")
    accounts.remove_key("grok")
    grok = next(p for p in accounts.list_providers() if p["id"] == "grok")
    assert grok["state"] == "not_configured"


def test_unknown_provider_raises() -> None:
    with pytest.raises(UnknownProvider):
        ModelAccounts().save_key("bing", "x")
    with pytest.raises(UnknownProvider):
        ModelAccounts().test_connection("bing")


def test_test_connection_without_a_key_says_so() -> None:
    result = ModelAccounts().test_connection("grok")
    assert result["ok"] is False
    assert "No key saved" in result["message"]


def test_test_connection_probes_the_saved_key(monkeypatch: pytest.MonkeyPatch) -> None:
    accounts = ModelAccounts()
    accounts.save_key("grok", "xai-key-123")
    monkeypatch.setattr("alpha.models.accounts.probe", lambda base_url, key: None)
    result = accounts.test_connection("grok")
    assert result == {"ok": True, "message": "Connected."}


def test_test_connection_reports_a_rejected_key(monkeypatch: pytest.MonkeyPatch) -> None:
    accounts = ModelAccounts()
    accounts.save_key("grok", "xai-key-bad")

    def fail(base_url: str, key: str) -> None:
        raise ProviderHTTPError("The key was rejected. Check it and try again.")

    monkeypatch.setattr("alpha.models.accounts.probe", fail)
    result = accounts.test_connection("grok")
    assert result["ok"] is False
    assert "rejected" in result["message"]
