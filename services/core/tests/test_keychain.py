"""A key is saved through `security -i` (stdin, never argv) and read back through
`find-generic-password`, against a fake `security` script on PATH — no real Keychain touched."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from alpha.models import keychain


@pytest.fixture
def fake_security(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A `security` stand-in backed by one file per (service, account); good enough to exercise
    add/find/delete without a real login Keychain."""
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    script = tmp_path / "security"
    script.write_text(
        "#!/bin/sh\n"
        f'STORE_DIR="{store_dir}"\n'
        'if [ "$1" = "-i" ]; then\n'
        "  read -r line\n"
        "  case \"$line\" in\n"
        "    add-generic-password*)\n"
        "      svc=$(echo \"$line\" | sed -n 's/.*-s \"\\([^\"]*\\)\".*/\\1/p')\n"
        "      val=$(echo \"$line\" | sed -n 's/.*-w \"\\(.*\\)\"$/\\1/p')\n"
        '      printf "%s" "$val" > "$STORE_DIR/$svc" ;;\n'
        "  esac\n"
        'elif [ "$1" = "find-generic-password" ]; then\n'
        '  svc="$3"\n'
        '  [ -f "$STORE_DIR/$svc" ] && cat "$STORE_DIR/$svc" || exit 44\n'
        'elif [ "$1" = "delete-generic-password" ]; then\n'
        '  svc="$3"\n'
        '  rm -f "$STORE_DIR/$svc"\n'
        "fi\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    return store_dir


def test_no_key_means_none(fake_security: Path) -> None:
    assert keychain.get_key("openrouter") is None
    assert not keychain.has_key("openrouter")
    assert keychain.last4("openrouter") is None


def test_set_then_get_then_delete(fake_security: Path) -> None:
    keychain.set_key("openrouter", "sk-or-abcdef1234")
    assert keychain.get_key("openrouter") == "sk-or-abcdef1234"
    assert keychain.has_key("openrouter")
    assert keychain.last4("openrouter") == "1234"
    keychain.delete_key("openrouter")
    assert keychain.get_key("openrouter") is None


def test_set_replaces_existing(fake_security: Path) -> None:
    keychain.set_key("grok", "first-key")
    keychain.set_key("grok", "second-key")
    assert keychain.get_key("grok") == "second-key"


def test_keys_are_isolated_per_provider(fake_security: Path) -> None:
    keychain.set_key("chatgpt", "a")
    keychain.set_key("claude", "b")
    assert keychain.get_key("chatgpt") == "a"
    assert keychain.get_key("claude") == "b"


def test_empty_key_is_refused(fake_security: Path) -> None:
    with pytest.raises(keychain.KeychainError):
        keychain.set_key("grok", "   ")


def test_newline_in_key_is_refused(fake_security: Path) -> None:
    with pytest.raises(keychain.KeychainError):
        keychain.set_key("grok", "line1\nline2")


def test_a_key_with_spaces_round_trips(fake_security: Path) -> None:
    # Escaping fidelity for quotes/backslashes depends on the real `security` binary's own
    # command parser, which this fake (a small shell/sed stand-in) does not fully emulate; this
    # only proves the common case (a key containing whitespace) is quoted and read back intact.
    tricky = "sk long key with spaces 1234"
    keychain.set_key("grok", tricky)
    assert keychain.get_key("grok") == tricky


def test_security_missing_from_path_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))  # empty dir, no `security` binary
    assert keychain.get_key("grok") is None
    with pytest.raises(keychain.KeychainError):
        keychain.set_key("grok", "x")
