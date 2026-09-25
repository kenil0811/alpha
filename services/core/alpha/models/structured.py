"""Structured inference through the model gateway's routes.

`fake` answers deterministically from request text (control fixture). `claude-code-cli` runs
the CLI non-agentically (no tools, one turn, settings ignored) with a JSON schema; the result's
`structured_output` is validated by the caller's Pydantic model and usage is recorded.
"""

from __future__ import annotations

import json
import os
import pwd
import subprocess
import time
from dataclasses import dataclass
from typing import Any

from alpha_contracts.builds import BuildUsage, CostBasis

from alpha.models.gateway import ModelGateway, ModelRoute


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
        timeout_seconds: int = 180,
    ) -> None:
        self._gateway = gateway
        self._binary = claude_binary
        self._path = tool_path
        self._home = home
        self._timeout = timeout_seconds

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
        if route.route_id != "claude-code-cli":
            raise InferenceError(
                "route_unavailable", f"no structured inference for {route.route_id}"
            )
        return self._claude_cli(route, system, prompt, schema, scope_kind, scope_ref)

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
        argv = [
            self._binary,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(schema),
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
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                env=env,
                stdin=subprocess.DEVNULL,
                timeout=self._timeout,
            )
        except FileNotFoundError as exc:
            raise InferenceError("cli_missing", f"claude CLI not found: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise InferenceError("timeout", f"model call exceeded {self._timeout}s") from exc
        elapsed = int((time.monotonic() - started) * 1000)
        line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("{")), None)
        if line is None:
            raise InferenceError(
                "cli_no_output", (proc.stderr or proc.stdout)[-300:] or "no output"
            )
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
