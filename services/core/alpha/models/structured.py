"""Structured inference through the model gateway's routes.

`fake` answers deterministically from request text (control fixture). `claude-code-cli` and
`chatgpt-codex-cli` run their CLI non-agentically (no tools, one turn, settings ignored) with a
JSON schema; `chatgpt-api`, `openrouter` and `grok` call an OpenAI-compatible HTTPS endpoint
directly with the key saved in the Keychain. Every route's result is validated by the caller's
Pydantic model against the full schema, and usage is recorded either way.
"""

from __future__ import annotations

import json
import os
import pwd
import re
import subprocess
import threading
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alpha_contracts.builds import BuildUsage, CostBasis

from alpha.models import claude_oauth, keychain
from alpha.models.gateway import ModelGateway, ModelRoute
from alpha.models.providers import ProviderHTTPError, chat_structured

# route_id -> (provider id the key/CLI is saved under in the Keychain, base URL for HTTP routes)
_HTTP_PROVIDER: dict[str, tuple[str, str]] = {
    "chatgpt-api": ("chatgpt_api", "https://api.openai.com/v1"),
    "openrouter": ("openrouter", "https://openrouter.ai/api/v1"),
    "grok": ("grok", "https://api.x.ai/v1"),
}

# The JSON Schema keywords the CLI's strict validator knows. Anything else (Pydantic's
# `discriminator`, a vendor extension) makes the CLI refuse the whole call before the model runs,
# so it is dropped; `format` is dropped too, since unknown formats are also refused. The caller's
# Pydantic model validates the result against the full schema afterwards.
_SCHEMA_KEYWORDS = frozenset(
    {
        "$schema", "$id", "$ref", "$defs", "$comment", "$anchor", "definitions",
        "type", "enum", "const", "title", "description", "default", "examples",
        "properties", "required", "additionalProperties", "patternProperties", "propertyNames",
        "minProperties", "maxProperties", "dependentRequired", "dependentSchemas",
        "items", "prefixItems", "minItems", "maxItems", "uniqueItems", "contains",
        "minContains", "maxContains", "unevaluatedItems", "unevaluatedProperties",
        "minLength", "maxLength", "pattern",
        "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
        "anyOf", "oneOf", "allOf", "not", "if", "then", "else",
        "readOnly", "writeOnly", "deprecated",
    }
)  # fmt: skip
_SCHEMA_MAPS = {"properties", "patternProperties", "$defs", "definitions", "dependentSchemas"}
_SCHEMA_LISTS = {"anyOf", "oneOf", "allOf", "prefixItems"}
_SCHEMA_ONE = {
    "items", "not", "if", "then", "else", "contains", "propertyNames",
    "additionalProperties", "unevaluatedProperties", "unevaluatedItems",
}  # fmt: skip


def cli_schema(schema: Any) -> Any:
    """A copy of `schema` holding only standard JSON Schema keywords, walked structurally so a
    property that happens to be named like a keyword is kept."""
    if not isinstance(schema, dict):
        return schema
    clean: dict[str, Any] = {}
    for key, value in schema.items():
        if key not in _SCHEMA_KEYWORDS:
            continue
        if key in _SCHEMA_MAPS and isinstance(value, dict):
            clean[key] = {name: cli_schema(sub) for name, sub in value.items()}
        elif key in _SCHEMA_LISTS and isinstance(value, list):
            clean[key] = [cli_schema(sub) for sub in value]
        elif key in _SCHEMA_ONE:
            clean[key] = cli_schema(value)
        else:
            clean[key] = value
    return clean


class InferenceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class StructuredResult:
    output: dict[str, Any]
    usage: BuildUsage
    model: str
    elapsed_ms: int
    raw_result_preview: str


class StructuredInference:
    def __init__(
        self,
        gateway: ModelGateway,
        *,
        claude_binary: str = "claude",
        tool_path: str = "/usr/bin:/bin",
        home: str | None = None,
        timeout_seconds: int = 300,
    ) -> None:
        self._gateway = gateway
        self._binary = claude_binary
        self._path = tool_path
        self._home = home
        self._timeout = timeout_seconds
        # Running CLI processes by scope_ref, so a person can stop a turn that is taking long.
        self._running: dict[str, subprocess.Popen[str]] = {}
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()

    def cancel(self, scope_ref: str) -> bool:
        """Stop the call running for `scope_ref`, if any. Returns whether one was running."""
        with self._lock:
            proc = self._running.get(scope_ref)
            if proc is None:
                return False
            self._cancelled.add(scope_ref)
        try:
            proc.kill()
        except OSError:
            pass
        return True

    def call(
        self,
        route: ModelRoute,
        *,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        scope_kind: str,
        scope_ref: str,
        fake: Any | None = None,
    ) -> StructuredResult:
        if route.route_id == "fake":
            if fake is None:
                raise InferenceError("route_unavailable", "fake route needs a fake responder")
            started = time.monotonic()
            output = fake(prompt)
            usage = BuildUsage(cost_basis=CostBasis.UNAVAILABLE, turns=1)
            self._gateway.record_usage(route.route_id, scope_kind, scope_ref, usage)
            return StructuredResult(
                output, usage, "fake", int((time.monotonic() - started) * 1000), ""
            )
        if route.route_id == "claude-code-cli":
            return self._claude_cli(route, system, prompt, schema, scope_kind, scope_ref)
        if route.route_id == "chatgpt-codex-cli":
            return self._codex_cli(route, system, prompt, schema, scope_kind, scope_ref)
        if route.route_id in _HTTP_PROVIDER:
            return self._http_provider(route, system, prompt, schema, scope_kind, scope_ref)
        raise InferenceError("route_unavailable", f"no structured inference for {route.route_id}")

    def _claude_cli(
        self,
        route: ModelRoute,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        scope_kind: str,
        scope_ref: str,
    ) -> StructuredResult:
        owner = pwd.getpwuid(os.getuid()).pw_name
        env = {
            "PATH": self._path,
            "HOME": self._home or pwd.getpwuid(os.getuid()).pw_dir,
            "USER": owner,
            "LOGNAME": owner,
            "LANG": "C.UTF-8",
            "TERM": "dumb",
            "DISABLE_AUTOUPDATER": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }
        # Default is the CLI's own sign-in (`claude auth login`): no key is passed, so the
        # person's logged-in session is used. Only when "Claude API" is the default provider in
        # Settings -> Models is its key read from the Keychain (falling back to Core's own
        # environment, e.g. a host that sets ANTHROPIC_API_KEY directly) and passed through.
        # Never logged. Without a Preferences store at all (some tests), the legacy
        # env-passthrough behaviour is kept.
        # ponytail: follows the default provider, not a per-session + Advanced choice of Claude
        # API; carry the account on ModelRoute if sessions need to pick it on their own.
        prefs = self._gateway.preferences
        api_key = None
        if prefs is not None and prefs.get("models.provider") == "claude_api":
            api_key = keychain.get_key("claude_api") or os.environ.get("ANTHROPIC_API_KEY")
        elif prefs is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key
        elif prefs is not None:
            # Signed in through Alpha (Settings -> Models -> Sign in): hand the CLI that token,
            # which wins over whatever the CLI's own login holds.
            oauth_token = claude_oauth.access_token()
            if oauth_token:
                env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
        argv = [
            self._binary,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(cli_schema(schema)),
            "--system-prompt",
            system,
            "--tools",
            "",
            "--max-turns",
            "2",
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--permission-prompts",
            "none",
        ]
        if route.model != "default":
            argv += ["--model", route.model]
        started = time.monotonic()
        try:
            proc = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            raise InferenceError("cli_missing", f"claude CLI not found: {exc}") from exc
        with self._lock:
            self._cancelled.discard(scope_ref)
            self._running[scope_ref] = proc
        try:
            stdout, stderr = proc.communicate(timeout=self._timeout)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            proc.communicate()
            raise InferenceError("timeout", f"model call exceeded {self._timeout}s") from exc
        finally:
            with self._lock:
                self._running.pop(scope_ref, None)
                stopped = scope_ref in self._cancelled
                self._cancelled.discard(scope_ref)
        if stopped:
            raise InferenceError("cancelled", "the call was stopped")
        elapsed = int((time.monotonic() - started) * 1000)
        line = next((ln for ln in stdout.splitlines() if ln.startswith("{")), None)
        if line is None:
            raise InferenceError("cli_no_output", (stderr or stdout)[-300:] or "no output")
        try:
            result = json.loads(line)
        except json.JSONDecodeError as exc:
            raise InferenceError("cli_bad_json", str(exc)) from exc
        usage = self._usage(result)
        self._gateway.record_usage(route.route_id, scope_kind, scope_ref, usage)
        text = str(result.get("result", ""))
        if "Not logged in" in text:
            raise InferenceError("cli_not_logged_in", text[:200])
        if result.get("is_error"):
            raise InferenceError("cli_error", text[:300])
        output = result.get("structured_output")
        if not isinstance(output, dict):
            raise InferenceError(
                "no_structured_output", text[:300] or "model returned no structured output"
            )
        models = list((result.get("modelUsage") or {}).keys())
        return StructuredResult(
            output, usage, models[0] if models else "unknown", elapsed, text[:300]
        )

    def _codex_cli(
        self,
        route: ModelRoute,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        scope_kind: str,
        scope_ref: str,
    ) -> StructuredResult:
        """ChatGPT via the Codex CLI (`codex login`), the person's sign-in choice. Codex's `exec`
        subcommand has no schema flag of its own, so the schema is folded into the prompt and the
        JSON object is picked out of the CLI's last answer; best-effort, unverified against a real
        `codex` binary in this environment."""
        owner = pwd.getpwuid(os.getuid()).pw_name
        env = {
            "PATH": self._path,
            "HOME": self._home or pwd.getpwuid(os.getuid()).pw_dir,
            "USER": owner,
            "LOGNAME": owner,
            "LANG": "C.UTF-8",
            "TERM": "dumb",
        }
        full_prompt = (
            f"{system}\n\nReply with exactly one JSON object matching this JSON Schema, and "
            f"nothing else, no prose, no code fence:\n{json.dumps(cli_schema(schema))}\n\n{prompt}"
        )
        argv = ["codex", "exec", "--json", "--skip-git-repo-check"]
        model = route.model if route.model != "default" else codex_model(env["HOME"])
        if model:
            argv += ["--model", model]
        argv.append(full_prompt)
        started = time.monotonic()
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                env=env,
                timeout=self._timeout,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            raise InferenceError("cli_missing", f"codex CLI not found: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise InferenceError("timeout", f"model call exceeded {self._timeout}s") from exc
        elapsed = int((time.monotonic() - started) * 1000)
        combined = f"{proc.stdout}\n{proc.stderr}"
        if "not logged in" in combined.lower() or "codex login" in proc.stderr.lower():
            raise InferenceError("cli_not_logged_in", (proc.stderr or proc.stdout)[:200])
        text, failure = codex_answer(proc.stdout)
        if text is None and failure:
            raise InferenceError("cli_error", failure[:300])
        if text is None:
            tail = (proc.stderr or proc.stdout)[-300:] or "no output"
            raise InferenceError("cli_no_output", tail)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise InferenceError("no_structured_output", text[:300])
        try:
            output = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise InferenceError("cli_bad_json", str(exc)) from exc
        if not isinstance(output, dict):
            raise InferenceError("no_structured_output", text[:300])
        usage = BuildUsage(
            turns=1, duration_ms=elapsed, cost_basis=CostBasis.SUBSCRIPTION_UNMETERED
        )
        self._gateway.record_usage(route.route_id, scope_kind, scope_ref, usage)
        return StructuredResult(output, usage, route.model, elapsed, text[:300])

    def _http_provider(
        self,
        route: ModelRoute,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        scope_kind: str,
        scope_ref: str,
    ) -> StructuredResult:
        keychain_provider, base_url = _HTTP_PROVIDER[route.route_id]
        api_key = keychain.get_key(keychain_provider)
        if not api_key:
            raise InferenceError(
                "no_key", f"no key saved for {route.provider} (Settings -> Models)"
            )
        try:
            output, usage, elapsed = chat_structured(
                base_url,
                api_key,
                route.model,
                system,
                prompt,
                cli_schema(schema),
                timeout=self._timeout,
            )
        except ProviderHTTPError as exc:
            raise InferenceError("provider_error", str(exc)) from exc
        self._gateway.record_usage(route.route_id, scope_kind, scope_ref, usage)
        return StructuredResult(output, usage, route.model, elapsed, json.dumps(output)[:300])

    @staticmethod
    def _usage(result: dict[str, Any]) -> BuildUsage:
        usage = result.get("usage") or {}
        models: dict[str, dict[str, Any]] = {}
        for name, entry in (result.get("modelUsage") or {}).items():
            if isinstance(entry, dict):
                models[name] = {k: entry.get(k) for k in ("inputTokens", "outputTokens", "costUSD")}
        return BuildUsage(
            input_tokens=int(usage.get("input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
            cache_read_input_tokens=int(usage.get("cache_read_input_tokens", 0) or 0),
            cache_creation_input_tokens=int(usage.get("cache_creation_input_tokens", 0) or 0),
            turns=int(result.get("num_turns", 0) or 0),
            duration_ms=int(result.get("duration_ms", 0) or 0),
            cost_usd=float(result["total_cost_usd"])
            if result.get("total_cost_usd") is not None
            else None,
            cost_basis=CostBasis.SUBSCRIPTION_UNMETERED,
            models=models,
        )


def codex_model(home: str) -> str | None:
    """The model to pass to `codex exec`, or None for Codex's own default. The ChatGPT app can
    leave a model in ~/.codex/config.toml that this CLI and account can't use (seen: a 400
    "not supported when using Codex with a ChatGPT account"); then the account's first listed
    model from Codex's own cache is used instead."""
    base = Path(home) / ".codex"
    try:
        cache = json.loads((base / "models_cache.json").read_text())
        listed = sorted(
            (m for m in cache.get("models", []) if m.get("visibility") == "list"),
            key=lambda m: m.get("priority", 0),
        )
    except (OSError, ValueError, AttributeError):
        return None
    slugs = [str(m["slug"]) for m in listed if m.get("slug")]
    if not slugs:
        return None
    try:
        configured = tomllib.loads((base / "config.toml").read_text()).get("model")
    except (OSError, tomllib.TOMLDecodeError):
        configured = None
    return None if configured in slugs else slugs[0]


def codex_answer(stdout: str) -> tuple[str | None, str | None]:
    """(last answer text, failure message) from `codex exec --json` events. Current Codex sends
    `item.completed` with an `agent_message` item; older ones sent `msg.message` / `text`."""
    text: str | None = None
    failure: str | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item")
        msg = event.get("msg")
        if isinstance(item, dict) and item.get("type") == "agent_message" and item.get("text"):
            text = str(item["text"])
        elif isinstance(msg, dict) and msg.get("message"):
            text = str(msg["message"])
        elif event.get("type") in ("turn.failed", "error"):
            raw = (event.get("error") or {}).get("message") if event.get("error") else None
            raw = raw or event.get("message") or ""
            try:  # the message is often itself an API error body
                raw = json.loads(raw)["error"]["message"]
            except (ValueError, TypeError, KeyError):
                pass
            failure = str(raw) or "Codex stopped with an error"
        elif event.get("text"):
            text = str(event["text"])
    return text, failure
