"""StructuredInference dispatch to the new routes: Claude's Console-vs-API-key auth mode, the
Codex CLI, and the OpenAI-compatible HTTP providers (chatgpt-api, openrouter, grok)."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from alpha.models import keychain
from alpha.models.gateway import ModelGateway
from alpha.models.preferences import Preferences
from alpha.models.providers import ProviderHTTPError
from alpha.models.structured import InferenceError, StructuredInference
from alpha.storage.control_store import ControlStore


def echo_env_cli(tmp_path: Path, name: str = "claude") -> Path:
    script = tmp_path / name
    script.write_text(
        "#!/bin/sh\n"
        'printf \'{"result": "ok", "structured_output": {"has_key": "%s"}}\\n\''
        ' "$ANTHROPIC_API_KEY"\n',
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


@pytest.fixture
def fake_security(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store_dir = tmp_path / "kstore"
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
        "fi\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{tmp_path}:/bin:/usr/bin")


def make_gateway(tmp_path: Path, routes: frozenset[str]) -> tuple[ModelGateway, Preferences]:
    store = ControlStore(tmp_path / "control.sqlite")
    prefs = Preferences(store)
    return ModelGateway(store, routes, preferences=prefs), prefs


def test_claude_console_mode_passes_no_key_even_if_core_env_has_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-core-env")
    gateway, prefs = make_gateway(tmp_path, frozenset({"claude-code-cli"}))
    assert prefs.get("models.provider") == "claude"
    inference = StructuredInference(gateway, claude_binary=str(echo_env_cli(tmp_path)))
    result = inference.call(
        gateway.route("claude-code-cli"),
        system="s",
        prompt="p",
        schema={"type": "object", "properties": {"has_key": {"type": "string"}}},
        scope_kind="assistant_turn",
        scope_ref="c1",
    )
    assert result.output["has_key"] == "", "console mode never leaks Core's own env var"


def test_claude_api_key_mode_uses_the_keychain(
    tmp_path: Path, fake_security: None
) -> None:
    gateway, prefs = make_gateway(tmp_path, frozenset({"claude-code-cli"}))
    prefs.update({"models.provider": "claude_api"})
    keychain.set_key("claude_api", "sk-ant-from-keychain")
    inference = StructuredInference(gateway, claude_binary=str(echo_env_cli(tmp_path)))
    result = inference.call(
        gateway.route("claude-code-cli"),
        system="s",
        prompt="p",
        schema={"type": "object", "properties": {"has_key": {"type": "string"}}},
        scope_kind="assistant_turn",
        scope_ref="c2",
    )
    assert result.output["has_key"] == "sk-ant-from-keychain"


def test_openrouter_route_calls_the_http_provider(
    tmp_path: Path, fake_security: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway, _ = make_gateway(tmp_path, frozenset({"openrouter"}))
    keychain.set_key("openrouter", "sk-or-test")
    inference = StructuredInference(gateway)

    def fake_chat_structured(base_url, api_key, model, system, prompt, schema, timeout=120):
        from alpha_contracts.builds import BuildUsage, CostBasis

        assert api_key == "sk-or-test"
        return {"ok": True}, BuildUsage(turns=1, cost_basis=CostBasis.PROVIDER_REPORTED), 5

    monkeypatch.setattr("alpha.models.structured.chat_structured", fake_chat_structured)
    result = inference.call(
        gateway.route("openrouter"),
        system="s",
        prompt="p",
        schema={"type": "object"},
        scope_kind="assistant_turn",
        scope_ref="c3",
    )
    assert result.output == {"ok": True}


def test_http_provider_without_a_saved_key_raises_no_key(
    tmp_path: Path, fake_security: None
) -> None:
    gateway, _ = make_gateway(tmp_path, frozenset({"grok"}))
    inference = StructuredInference(gateway)
    with pytest.raises(InferenceError) as exc_info:
        inference.call(
            gateway.route("grok"),
            system="s",
            prompt="p",
            schema={"type": "object"},
            scope_kind="assistant_turn",
            scope_ref="c4",
        )
    assert exc_info.value.code == "no_key"


def test_http_provider_error_is_wrapped(
    tmp_path: Path, fake_security: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway, _ = make_gateway(tmp_path, frozenset({"grok"}))
    keychain.set_key("grok", "xai-bad")
    inference = StructuredInference(gateway)

    def fail(*a, **k):
        raise ProviderHTTPError("The key was rejected. Check it and try again.")

    monkeypatch.setattr("alpha.models.structured.chat_structured", fail)
    with pytest.raises(InferenceError) as exc_info:
        inference.call(
            gateway.route("grok"),
            system="s",
            prompt="p",
            schema={"type": "object"},
            scope_kind="assistant_turn",
            scope_ref="c5",
        )
    assert exc_info.value.code == "provider_error"
    assert "rejected" in str(exc_info.value)


def test_codex_cli_missing_raises_cli_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "/nonexistent")
    gateway, _ = make_gateway(tmp_path, frozenset({"chatgpt-codex-cli"}))
    inference = StructuredInference(gateway)
    with pytest.raises(InferenceError) as exc_info:
        inference.call(
            gateway.route("chatgpt-codex-cli"),
            system="s",
            prompt="p",
            schema={"type": "object"},
            scope_kind="assistant_turn",
            scope_ref="c6",
        )
    assert exc_info.value.code == "cli_missing"


def test_codex_cli_parses_the_last_json_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Best-effort: the real Codex CLI's `exec --json` event shape isn't verified here (no
    `codex` binary available); this fixture mimics the assumed shape (a stream of JSON lines,
    the last one carrying the answer under msg.message), built with json.dumps so it is valid
    JSON regardless of what the answer text itself contains."""
    events = [
        {"type": "start"},
        {"msg": {"message": 'here you go: {"answer": "42"}'}},
    ]
    body = "\n".join(json.dumps(e) for e in events)
    script = tmp_path / "codex"
    script.write_text(f"#!/bin/sh\ncat <<'EOF'\n{body}\nEOF\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    gateway, _ = make_gateway(tmp_path, frozenset({"chatgpt-codex-cli"}))
    inference = StructuredInference(gateway, tool_path=f"{tmp_path}:/bin:/usr/bin")
    result = inference.call(
        gateway.route("chatgpt-codex-cli"),
        system="s",
        prompt="p",
        schema={"type": "object", "properties": {"answer": {"type": "string"}}},
        scope_kind="assistant_turn",
        scope_ref="c7",
    )
    assert result.output == {"answer": "42"}
