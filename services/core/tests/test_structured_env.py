"""An ANTHROPIC_API_KEY present in Core's own environment reaches the `claude` subprocess, so a
person can authenticate that way when the Claude subscription route is disabled."""

from __future__ import annotations

import stat
from pathlib import Path

from alpha.models.gateway import ModelGateway
from alpha.models.structured import StructuredInference
from alpha.storage.control_store import ControlStore


def echo_env_cli(tmp_path: Path) -> Path:
    """A fake `claude` binary that reports whether ANTHROPIC_API_KEY reached it."""
    script = tmp_path / "claude"
    script.write_text(
        "#!/bin/sh\n"
        'printf \'{"result": "ok", "structured_output": {"has_key": "%s"}}\\n\''
        ' "$ANTHROPIC_API_KEY"\n',
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def test_anthropic_api_key_is_passed_through_when_present(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-secret")
    gateway = ModelGateway(
        ControlStore(tmp_path / "control.sqlite"), frozenset({"claude-code-cli"})
    )
    inference = StructuredInference(gateway, claude_binary=str(echo_env_cli(tmp_path)))
    result = inference.call(
        gateway.route("claude-code-cli"),
        system="s",
        prompt="p",
        schema={"type": "object", "properties": {"has_key": {"type": "string"}}},
        scope_kind="assistant_turn",
        scope_ref="conv_env",
    )
    assert result.output["has_key"] == "sk-test-secret"


def test_no_key_set_means_none_passed(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    gateway = ModelGateway(
        ControlStore(tmp_path / "control.sqlite"), frozenset({"claude-code-cli"})
    )
    inference = StructuredInference(gateway, claude_binary=str(echo_env_cli(tmp_path)))
    result = inference.call(
        gateway.route("claude-code-cli"),
        system="s",
        prompt="p",
        schema={"type": "object", "properties": {"has_key": {"type": "string"}}},
        scope_kind="assistant_turn",
        scope_ref="conv_env2",
    )
    assert result.output["has_key"] == ""
