"""Settings -> Models: the connection monitor answers from a real `claude` binary on PATH (a
script standing in for it here) and says plainly what is wrong: missing, too old, signed out,
last call failed, or connected. It never returns a credential."""

from __future__ import annotations

import json
import re
import stat
import time
from pathlib import Path

import pytest
from alpha.models import connection as connection_module
from alpha.models.connection import (
    MIN_SUPPORTED_VERSION,
    REQUIRED_FLAGS,
    UNLISTED_FLAGS,
    ConnectionMonitor,
    LoginUnavailable,
)
from alpha.models.gateway import ModelGateway
from alpha.models.structured import InferenceError, StructuredInference
from alpha.storage.control_store import ControlStore

CORE = Path(__file__).resolve().parents[1] / "alpha"

FAKE_CLAUDE = r"""#!/bin/sh
dir=$(dirname "$0")
case "$1" in
  --version) cat "$dir/version" ;;
  --help) cat "$dir/help" ;;
  auth)
    if [ "$2" = status ]; then
      if [ -f "$dir/logged_in" ]; then
        cat "$dir/auth.json"
      else
        echo '{"loggedIn":false,"authMethod":"none"}'; exit 1
      fi
    elif [ "$2" = login ]; then
      touch "$dir/login_started"; sleep 1; touch "$dir/logged_in"; sleep 30
    fi ;;
  -p)
    for arg in "$@"; do
      if [ "$arg" = --permission-prompts ] && ! grep -q -- --permission-prompts "$dir/help"; then
        echo "error: unknown option '--permission-prompts'" >&2; exit 1
      fi
    done
    if [ -f "$dir/logged_in" ]; then
      cat "$dir/result.json"
    else
      echo '{"type":"result","is_error":true,"result":"Not logged in · Please run /login"}'
    fi ;;
esac
"""
SIGNED_IN = {
    "loggedIn": True,
    "authMethod": "claude.ai",
    "email": "person@example.com",
    "orgName": "Person",
    "subscriptionType": "max",
    "accessToken": "sk-ant-secret",
}
CALL_OK = {
    "type": "result",
    "is_error": False,
    "result": "",
    "structured_output": {"ok": True},
    "usage": {"output_tokens": 3},
    "num_turns": 1,
    "duration_ms": 1234,
}
NEW_HELP = "Usage: claude [options]\n" + "\n".join(f"  {f} <x>  something" for f in REQUIRED_FLAGS)
# What 2.1.223 lists: no --permission-prompts and no --restricted.
OLD_HELP = "\n".join(
    f"  {f}" for f in REQUIRED_FLAGS if f not in ("--permission-prompts", "--restricted")
)


def fake_cli(tmp_path: Path, *, version: str, help_text: str, logged_in: bool) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "claude"
    script.write_text(FAKE_CLAUDE, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    (bin_dir / "version").write_text(f"{version} (Claude Code)\n", encoding="utf-8")
    (bin_dir / "help").write_text(help_text, encoding="utf-8")
    (bin_dir / "auth.json").write_text(json.dumps(SIGNED_IN), encoding="utf-8")
    (bin_dir / "result.json").write_text(json.dumps(CALL_OK), encoding="utf-8")
    if logged_in:
        (bin_dir / "logged_in").touch()
    return bin_dir


def monitor(
    tmp_path: Path, bin_dir: Path | None, routes: frozenset[str] = frozenset({"claude-code-cli"})
) -> tuple[ConnectionMonitor, StructuredInference]:
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(store, routes)
    path = f"{bin_dir}:/usr/bin:/bin" if bin_dir else str(tmp_path / "empty")
    inference = StructuredInference(gateway, tool_path=path, timeout_seconds=20)
    return ConnectionMonitor(store, gateway, inference), inference


def test_connected_reports_version_account_and_never_a_token(tmp_path: Path) -> None:
    bin_dir = fake_cli(tmp_path, version="2.1.283", help_text=NEW_HELP, logged_in=True)
    snap, _ = monitor(tmp_path, bin_dir)
    got = snap.snapshot()
    assert got["status"] == "connected" and got["fix"] is None
    assert got["cli_path"] == str(bin_dir / "claude")
    assert (got["cli_version"], got["min_supported_version"]) == ("2.1.283", MIN_SUPPORTED_VERSION)
    assert got["version_supported"] is True and got["missing_flags"] == []
    assert got["logged_in"] is True
    assert got["account"] == {
        "auth_method": "claude.ai",
        "email": "person@example.com",
        "organization": "Person",
        "plan": "max",
    }
    assert "sk-ant-secret" not in json.dumps(got), "a credential never leaves the monitor"
    assert got["last_successful_call_at"] is None and got["last_error"] is None


def test_missing_cli(tmp_path: Path) -> None:
    got = monitor(tmp_path, None)[0].snapshot()
    assert got["status"] == "cli_missing" and not got["cli_found"]
    assert "Install Claude Code" in got["fix"]


def test_too_old_cli_names_the_missing_flags_and_the_fix(tmp_path: Path) -> None:
    bin_dir = fake_cli(tmp_path, version="2.1.223", help_text=OLD_HELP, logged_in=True)
    snap, inference = monitor(tmp_path, bin_dir)
    got = snap.snapshot()
    assert got["status"] == "cli_too_old"
    assert got["missing_flags"] == ["--permission-prompts", "--restricted"]
    assert got["version_supported"] is False
    assert "claude update" in got["fix"]
    # A real call says why, instead of "no output".
    with pytest.raises(InferenceError, match="unknown option") as failed:
        inference.call(
            snap._gateway.route("claude-code-cli"),
            system="s",
            prompt="p",
            schema={"type": "object"},
            scope_kind="assistant_turn",
            scope_ref="conv_1",
        )
    assert failed.value.code == "cli_too_old"
    outcome = snap.check()["check"]
    assert outcome["ok"] is False and outcome["code"] == "cli_too_old"
    assert inference.last_failure is not None and inference.last_failure["code"] == "cli_too_old"


def test_signed_out_then_a_supervised_sign_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(connection_module, "LOGIN_POLL_SECONDS", 0.2)
    bin_dir = fake_cli(tmp_path, version="2.1.283", help_text=NEW_HELP, logged_in=False)
    snap, _ = monitor(tmp_path, bin_dir)
    got = snap.snapshot()
    assert got["status"] == "signed_out" and got["logged_in"] is False and got["account"] is None
    assert "Sign in" in got["fix"]
    outcome = snap.check()
    assert outcome["check"]["code"] == "cli_not_logged_in"
    # The CLI answered (in JSON) but the call did not work: not a successful call.
    assert outcome["last_successful_call_at"] is None

    started = snap.login()
    assert started["login"]["state"] == "waiting"
    assert snap.login()["login"]["started_at"] == started["login"]["started_at"], "one at a time"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and snap.snapshot()["login"]["state"] == "waiting":
        time.sleep(0.2)
    after = snap.snapshot()
    assert (bin_dir / "login_started").exists()
    assert after["login"]["state"] == "signed_in", "the login process is stopped once signed in"
    assert after["logged_in"] is True
    # The earlier failure is still the newest call, so the page says so until a call works.
    assert after["status"] == "last_call_failed"
    assert snap.check()["status"] == "connected"


def test_last_call_failed_until_a_later_call_succeeds(tmp_path: Path) -> None:
    bin_dir = fake_cli(tmp_path, version="2.1.283", help_text=NEW_HELP, logged_in=True)
    snap, inference = monitor(tmp_path, bin_dir)
    inference.last_failure = {
        "code": "timeout",
        "message": "model call exceeded 300s",
        "at": "2026-09-27T10:00:00Z",
    }
    got = snap.snapshot()
    assert got["status"] == "last_call_failed"
    assert got["last_error"]["message"] == "model call exceeded 300s"
    checked = snap.check()
    assert checked["check"]["ok"] is True
    assert checked["status"] == "connected" and checked["last_error"] is None
    assert checked["last_successful_call_at"] > "2026-09-27T10:00:00Z"
    assert isinstance(checked["last_call_latency_ms"], int)


def test_not_used_when_the_route_is_off_and_no_login_without_a_cli(tmp_path: Path) -> None:
    snap, _ = monitor(tmp_path, None, routes=frozenset({"fake"}))
    assert snap.snapshot()["status"] == "not_used"
    assert snap.check()["check"]["ok"] is False
    with pytest.raises(LoginUnavailable):
        snap.login()


def test_required_flags_cover_every_flag_alpha_passes() -> None:
    """The too-old test is only as good as this list: every flag literal at the CLI call sites
    must be in it (or known to be unlisted by --help)."""
    passed: set[str] = set()
    for source in (CORE / "models" / "structured.py", CORE / "builds" / "harness_claude_cli.py"):
        passed |= set(re.findall(r'"(--[a-zA-Z-]+)"', source.read_text(encoding="utf-8")))
    assert passed, "found the call sites"
    assert passed <= set(REQUIRED_FLAGS) | set(UNLISTED_FLAGS), passed - set(REQUIRED_FLAGS)
