"""Claude Code CLI harness (founder decision 2026-09-25: subscription route, internal use only).

Runs `claude -p` headless in the build workspace with:
- a private config home when it can authenticate, otherwise the user's home with every ambient
  setting source ignored (`--setting-sources ""`), no MCP servers, no session persistence;
- `--restricted`: file tools confined to the workspace, bypass mode refused, code-running tools
  only if named; `--permission-prompts none`: anything that would prompt is denied;
- an explicit tool list and a narrow Bash allowlist for compiling the candidate with the
  platform interpreter only;
- `--max-turns` and `--max-budget-usd` from the build budget, and the route's model.

Stream-json lines are normalized into harness events; the final result message supplies usage.
The CLI's own final prose never decides success: Core validates the package independently.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from alpha_contracts.builds import (
    BuildDiagnostic,
    BuildResultStatus,
    BuildUsage,
    CostBasis,
    FailureCategory,
)

from alpha.builds.harness import (
    HarnessCapabilities,
    HarnessEvent,
    HarnessInputs,
    HarnessOutcome,
)

PACKAGE_CONTRACT = """You are building a small pure Python package for the Alpha platform.

Write ONLY inside the directory `package/` of the current working directory. Required layout:
- package/app.yaml — declarative contract (contract_version '0.2', app_id, name, description,
  runtime_profile: platform-runtime-3.13.9, sdk_version: none, and `actions`).
- package/src/<module>.py — plain Python 3.13 with no third-party imports and no I/O, network,
  subprocess, environment or file access. Pure functions only.
- Optional package/tests/ — supplementary tests (not the acceptance evidence).

Each action in app.yaml has: id, title, description, handler (module:function inside src/),
input_schema and output_schema (JSON Schema objects with explicit required fields),
capability_requirements: [], effect_class: none, invocable_from: [assistant],
timeout_seconds, retry_class: pure.

The function must accept keyword arguments matching input_schema properties and return a dict
matching output_schema. Verify your code compiles with the platform interpreter given below.
Do not modify anything outside package/. Do not create git repositories. Finish by stating the
action id(s) you implemented.
"""


@dataclass
class ClaudeCliSession:
    session_ref: str
    process: subprocess.Popen[str]
    config_home: Path
    started_at: float
    result_message: dict[str, Any] | None = None
    stderr_tail: list[str] = field(default_factory=list)
    cancelled: bool = False
    saw_auth_error: bool = False
    lines_seen: int = 0


class ClaudeCliHarness:
    def __init__(
        self,
        *,
        claude_binary: str | None = None,
        platform_python: Path | None = None,
        config_home_strategy: str = "user_default_settings_ignored",
    ) -> None:
        self._binary = claude_binary or shutil.which("claude") or "claude"
        self._python = platform_python or Path(sys.executable)
        self._strategy = config_home_strategy

    def capabilities(self) -> HarnessCapabilities:
        version = "unknown"
        try:
            out = subprocess.run(
                [self._binary, "--version"], capture_output=True, text=True, timeout=20
            )
            version = out.stdout.strip().split()[0] if out.stdout.strip() else version
        except (OSError, subprocess.TimeoutExpired):
            version = "unavailable"
        return HarnessCapabilities(
            name="claude-code-cli",
            version=version,
            cancel=True,
            resume=False,
            usage_reporting=True,
            structured_events=True,
            notes=(
                "subscription login owned by the CLI; platform cannot inject a scoped credential",
                f"config home strategy: {self._strategy}",
            ),
        )

    # ----- lifecycle --------------------------------------------------------------------

    def start(self, inputs: HarnessInputs) -> ClaudeCliSession:
        workspace = inputs.workspace
        (workspace / "package").mkdir(parents=True, exist_ok=True)
        config_home = workspace / ".claude-home"
        config_home.mkdir(exist_ok=True)
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", str(workspace)),
            "LANG": "C.UTF-8",
            "TERM": "dumb",
            "CI": "1",
            "DISABLE_AUTOUPDATER": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }
        # The CLI resolves its subscription login by account name; without USER it reports
        # "Not logged in" (measured 2026-09-25).
        for key in ("USER", "LOGNAME"):
            if key in os.environ:
                env[key] = os.environ[key]
        if self._strategy == "private_config_home":
            env["CLAUDE_CONFIG_DIR"] = str(config_home)
        prompt = self._prompt(inputs)
        budget = inputs.request.budget
        argv = [
            self._binary,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--restricted",
            "--permission-mode",
            "acceptEdits",
            "--permission-prompts",
            "none",
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--tools",
            "Read,Write,Edit,Glob,Grep,Bash",
            "--allowedTools",
            f"Bash({self._python} -m py_compile:*)",
            f"Bash({self._python} -c:*)",
            f"Bash({self._python} -m unittest:*)",
            "Bash(ls:*)",
            "Bash(cat:*)",
            "--max-turns",
            str(budget.max_turns),
            "--model",
            inputs.model,
        ]
        if budget.max_cost_usd is not None:
            argv += ["--max-budget-usd", str(budget.max_cost_usd)]
        process = subprocess.Popen(
            argv,
            cwd=str(workspace),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        (workspace / "harness.argv.json").write_text(
            json.dumps(
                {
                    "argv": [
                        a if not a.startswith("You are building") else "<prompt>" for a in argv
                    ],
                    "env_keys": sorted(env),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return ClaudeCliSession(
            session_ref=f"claude-cli-{process.pid}",
            process=process,
            config_home=config_home,
            started_at=time.monotonic(),
        )

    def events(self, session: ClaudeCliSession) -> Iterator[HarnessEvent]:
        assert session.process.stdout is not None
        yield HarnessEvent(
            "harness.started", {"harness": "claude-code-cli", "pid": session.process.pid}
        )
        for raw in session.process.stdout:
            line = raw.strip()
            if not line:
                continue
            session.lines_seen += 1
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                yield HarnessEvent("harness.stdout", {"line": line[:500]})
                continue
            yield from self._normalize(session, message)
        session.process.wait()
        if session.process.stderr is not None:
            tail = session.process.stderr.read()[-4000:]
            if tail:
                session.stderr_tail = tail.splitlines()[-40:]

    def cancel(self, session: ClaudeCliSession) -> None:
        session.cancelled = True
        if session.process.poll() is None:
            session.process.terminate()
            try:
                session.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                session.process.kill()

    def result(self, session: ClaudeCliSession) -> HarnessOutcome:
        exit_code = session.process.poll()
        usage = self._usage(session.result_message)
        if session.cancelled:
            return HarnessOutcome(
                BuildResultStatus.CANCELLED, usage, FailureCategory.CANCELLED, exit_code=exit_code
            )
        diagnostics: list[BuildDiagnostic] = []
        final = session.result_message or {}
        text = str(final.get("result", ""))
        if session.saw_auth_error or "Not logged in" in text:
            diagnostics.append(
                BuildDiagnostic(level="error", code="cli_not_logged_in", message=text[:300])
            )
            return HarnessOutcome(
                BuildResultStatus.FAILED,
                usage,
                FailureCategory.HARNESS_AUTH,
                diagnostics,
                text,
                exit_code,
            )
        if session.lines_seen == 0:
            msg = " ".join(session.stderr_tail)[:300] or "no output from claude CLI"
            diagnostics.append(BuildDiagnostic(level="error", code="cli_no_output", message=msg))
            return HarnessOutcome(
                BuildResultStatus.FAILED,
                usage,
                FailureCategory.HARNESS_UNAVAILABLE,
                diagnostics,
                "",
                exit_code,
            )
        subtype = str(final.get("subtype", ""))
        if final.get("is_error") or subtype.startswith("error"):
            code = "cli_error_" + (subtype or "unknown")
            category = (
                FailureCategory.BUDGET_EXHAUSTED
                if "max_turns" in subtype or "budget" in subtype
                else FailureCategory.HARNESS_ERROR
            )
            diagnostics.append(BuildDiagnostic(level="error", code=code, message=text[:300]))
            return HarnessOutcome(
                BuildResultStatus.FAILED, usage, category, diagnostics, text, exit_code
            )
        if exit_code not in (0, None):
            diagnostics.append(
                BuildDiagnostic(level="error", code="cli_exit_nonzero", message=f"exit {exit_code}")
            )
            return HarnessOutcome(
                BuildResultStatus.FAILED,
                usage,
                FailureCategory.HARNESS_ERROR,
                diagnostics,
                text,
                exit_code,
            )
        return HarnessOutcome(
            BuildResultStatus.CANDIDATE, usage, None, diagnostics, text, exit_code
        )

    # ----- helpers -----------------------------------------------------------------------

    def _prompt(self, inputs: HarnessInputs) -> str:
        examples = json.dumps(inputs.acceptance_examples, indent=2)
        return (
            f"{PACKAGE_CONTRACT}\nPlatform interpreter: {self._python}\n\n"
            f"GOAL (from the user, plain language):\n{inputs.goal}\n\n"
            f"ADDITIONAL INSTRUCTIONS:\n{inputs.instructions}\n\n"
            "ACCEPTANCE EXAMPLES (inputs and expected outputs your function must satisfy):\n"
            f"{examples}\n"
        )

    def _normalize(
        self, session: ClaudeCliSession, message: dict[str, Any]
    ) -> Iterator[HarnessEvent]:
        kind = message.get("type")
        if kind == "system":
            if message.get("subtype") != "init":
                return  # progress-only system messages (e.g. thinking token counters)
            yield HarnessEvent(
                "harness.system",
                {
                    "subtype": message.get("subtype"),
                    "model": message.get("model"),
                    "tools": message.get("tools"),
                    "permission_mode": message.get("permissionMode"),
                },
            )
        elif kind == "assistant":
            content = (message.get("message") or {}).get("content") or []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text = str(block.get("text", ""))
                    if "Not logged in" in text:
                        session.saw_auth_error = True
                    yield HarnessEvent("harness.assistant_text", {"text": text[:2000]})
                elif block.get("type") == "tool_use":
                    inp = block.get("input") or {}
                    summary = {
                        k: (v[:200] if isinstance(v, str) else v)
                        for k, v in inp.items()
                        if k in ("file_path", "command", "pattern", "path")
                    }
                    yield HarnessEvent(
                        "harness.tool_use", {"tool": block.get("name"), "input": summary}
                    )
        elif kind == "user":
            content = (message.get("message") or {}).get("content") or []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    result = block.get("content")
                    text = result if isinstance(result, str) else json.dumps(result)[:300]
                    yield HarnessEvent(
                        "harness.tool_result",
                        {"is_error": bool(block.get("is_error")), "preview": str(text)[:300]},
                    )
        elif kind == "result":
            session.result_message = message
            if "Not logged in" in str(message.get("result", "")):
                session.saw_auth_error = True
            yield HarnessEvent(
                "harness.result",
                {
                    "subtype": message.get("subtype"),
                    "is_error": message.get("is_error"),
                    "num_turns": message.get("num_turns"),
                    "duration_ms": message.get("duration_ms"),
                    "total_cost_usd": message.get("total_cost_usd"),
                    "result_preview": str(message.get("result", ""))[:500],
                },
            )
        else:
            yield HarnessEvent("harness.message", {"type": kind})

    @staticmethod
    def _usage(result: dict[str, Any] | None) -> BuildUsage:
        if not result:
            return BuildUsage(cost_basis=CostBasis.UNAVAILABLE)
        usage = result.get("usage") or {}
        models = {}
        for name, entry in (result.get("modelUsage") or {}).items():
            if isinstance(entry, dict):
                models[name] = {
                    k: entry.get(k)
                    for k in (
                        "inputTokens",
                        "outputTokens",
                        "cacheReadInputTokens",
                        "cacheCreationInputTokens",
                        "costUSD",
                    )
                }
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
