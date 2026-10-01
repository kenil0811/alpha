"""Settings -> Models account state: keychain-backed, a fake `security` on PATH, no CLI needed
for the key-only providers (OpenRouter, Grok)."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from alpha.models.accounts import ModelAccounts, SignInUnavailable, UnknownProvider
from alpha.models.providers import ProviderHTTPError


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
    assert ids == {"claude", "claude_api", "chatgpt", "chatgpt_api", "openrouter", "grok", "groq"}


def test_claude_defaults_to_console_and_needs_sign_in_without_the_cli() -> None:
    described = next(p for p in ModelAccounts().list_providers() if p["id"] == "claude")
    assert described["state"] == "cli_missing"  # no `claude` on PATH in this test


def test_claude_api_is_its_own_key_row() -> None:
    accounts = ModelAccounts()
    row = next(p for p in accounts.list_providers() if p["id"] == "claude_api")
    assert row["state"] == "not_configured"
    accounts.save_key("claude_api", "sk-ant-test")
    rows = {p["id"]: p["state"] for p in accounts.list_providers()}
    assert rows["claude_api"] == "key_saved"
    assert rows["claude"] == "cli_missing"  # the sign-in row is untouched by a key


def test_claude_sign_in_opens_the_browser_page_and_waits_for_a_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[str] = []
    monkeypatch.setattr("alpha.models.claude_oauth.open_in_browser", opened.append)
    row = ModelAccounts().sign_in("claude")
    assert row["needs_code"] is True
    assert opened and opened[0].startswith("https://claude.ai/oauth/authorize?")


def test_sign_in_is_refused_for_key_rows_and_a_missing_cli() -> None:
    with pytest.raises(SignInUnavailable):
        ModelAccounts().sign_in("claude_api")
    with pytest.raises(SignInUnavailable, match="Install Codex"):
        ModelAccounts().sign_in("chatgpt")  # no `codex` on PATH in this test


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
    monkeypatch.setattr("alpha.models.accounts.probe", lambda base_url, key, headers=None: None)
    result = accounts.test_connection("grok")
    assert result == {"ok": True, "message": "Connected."}


def test_test_connection_reports_a_rejected_key(monkeypatch: pytest.MonkeyPatch) -> None:
    accounts = ModelAccounts()
    accounts.save_key("grok", "xai-key-bad")

    def fail(base_url: str, key: str, headers: object = None) -> None:
        raise ProviderHTTPError("The key was rejected. Check it and try again.")

    monkeypatch.setattr("alpha.models.accounts.probe", fail)
    result = accounts.test_connection("grok")
    assert result["ok"] is False
    assert "rejected" in result["message"]


def test_reconnect_signs_claude_out(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("alpha.models.claude_oauth.sign_out", lambda: calls.append("out"))
    ModelAccounts().reconnect("claude")
    assert calls == ["out"]


def _script(path: Path, body: str) -> Path:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_install_links_the_codex_that_ships_with_the_chatgpt_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _script(tmp_path / "bundled-codex", 'echo "Logged in using ChatGPT"\n')
    monkeypatch.setattr("alpha.models.accounts.CODEX_BUNDLES", (str(bundle),))
    home = tmp_path / "home"
    accounts = ModelAccounts(tool_path=f"{home}/.local/bin:/bin:/usr/bin", home=str(home))
    row = accounts.install("chatgpt")
    assert (home / ".local/bin/codex").resolve() == bundle.resolve()
    assert row["state"] == "connected"  # already signed in through the app


def test_install_falls_back_to_npm_in_the_background(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("alpha.models.accounts.CODEX_BUNDLES", ())
    tools = tmp_path / "tools"
    tools.mkdir()
    home = tmp_path / "home"
    # A fake npm that "installs" codex where `--prefix` says.
    _script(
        tools / "npm",
        'mkdir -p "$4/bin"\n'
        'printf \'#!/bin/sh\\necho "Not logged in"\\nexit 1\\n\' > "$4/bin/codex"\n'
        'chmod +x "$4/bin/codex"\n',
    )
    accounts = ModelAccounts(tool_path=f"{home}/.local/bin:{tools}:/bin:/usr/bin", home=str(home))
    accounts.install("chatgpt")
    accounts._installs["chatgpt"].wait(timeout=10)
    row = next(p for p in accounts.list_providers() if p["id"] == "chatgpt")
    assert row["installing"] is False and row["install_failed"] is False
    assert row["state"] == "needs_sign_in"  # installed; Connect is next


def test_install_without_npm_opens_the_install_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("alpha.models.accounts.CODEX_BUNDLES", ())
    opened: list[str] = []
    monkeypatch.setattr("alpha.models.claude_oauth.open_in_browser", opened.append)
    accounts = ModelAccounts(tool_path="/bin:/usr/bin", home=str(tmp_path))
    with pytest.raises(SignInUnavailable, match="install page"):
        accounts.install("chatgpt")
    assert opened == ["https://github.com/openai/codex"]
