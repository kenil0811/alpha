"""Codex CLI harness: ChatGPT signed in with Codex (`codex login`), the person's choice.

Runs `codex exec` headless in the build workspace, modelled on harness_claude_cli.py:
- `--sandbox workspace-write`: shell commands run in Codex's OS sandbox, writes confined to the
  workspace, no network; `--ignore-user-config --ignore-rules --ephemeral`: the person's own
  Codex config, rules and session history play no part;
- the same package contract and prompt as the Claude harness, and the route's model (`-m`).

JSONL events are normalized into harness events; `turn.completed` supplies usage. The CLI's
own final prose never decides success: Core validates the package independently.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Iterator
from typing import Any

from alpha_contracts.builds import (
    BuildDiagnostic,
    BuildResultStatus,
    BuildUsage,
    CostBasis,
    FailureCategory,
)

from alpha.builds.harness import HarnessCapabilities, HarnessEvent, HarnessInputs, HarnessOutcome
from alpha.builds.harness_claude_cli import ClaudeCliHarness, ClaudeCliSession
from alpha.builds.validate import write_validate_script

AUTH_MARKERS = ("not logged in", "codex login", "401 unauthorized", "please log in")

# Codex has no web tools inside its sandbox; the contract's WebFetch/WebSearch lines don't apply.
CODEX_NOTE = (
    "\nThis session has no WebFetch or WebSearch: build from the goal and the reference files. "
    "Shell commands run in a sandbox that can write only inside the current directory.\n"
)


def is_auth_failure(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in AUTH_MARKERS)


class CodexCliHarness(ClaudeCliHarness):
    """Reuses the Claude harness's prompt and cancel; runs `codex exec` instead."""

    def __init__(self, *, codex_binary: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._binary = codex_binary or shutil.which("codex") or "codex"

    def capabilities(self) -> HarnessCapabilities:
        version = "unknown"
        try:
            out = subprocess.run(
                [self._binary, "--version"], capture_output=True, text=True, timeout=20
            )
            version = out.stdout.strip().split()[-1] if out.stdout.strip() else version
        except (OSError, subprocess.TimeoutExpired):
            version = "unavailable"
        return HarnessCapabilities(
            name="codex-cli",
            version=version,
            cancel=True,
            resume=False,
            usage_reporting=True,
            structured_events=True,
            notes=("ChatGPT sign-in owned by the Codex CLI; no turn or cost cap, time cap only",),
        )

    def start(self, inputs: HarnessInputs) -> ClaudeCliSession:
        workspace = inputs.workspace
        (workspace / "package").mkdir(parents=True, exist_ok=True)
        write_validate_script(workspace, self._python)
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", str(workspace)),
            "LANG": "C.UTF-8",
            "TERM": "dumb",
            "CI": "1",
        }
        for key in ("USER", "LOGNAME", "CODEX_HOME"):
            if key in os.environ:
                env[key] = os.environ[key]
        argv = [
            self._binary,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--sandbox",
            "workspace-write",
            "--cd",
            str(workspace),
        ]
        if inputs.model and inputs.model != "default":
            argv += ["--model", inputs.model]
        argv.append(self._prompt(inputs) + CODEX_NOTE)
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
            json.dumps({"argv": [*argv[:-1], "<prompt>"], "env_keys": sorted(env)}, indent=2),
            encoding="utf-8",
        )
        session = ClaudeCliSession(
            session_ref=f"codex-cli-{process.pid}",
            process=process,
            config_home=workspace,
            started_at=time.monotonic(),
        )

        def drain() -> None:
            # Read stderr while the CLI runs: a full pipe would otherwise stall it.
            stream = process.stderr
            if stream is None:
                return
            tail = ""
            try:
                for chunk in iter(lambda: stream.read(4096), ""):
                    tail = (tail + chunk)[-4000:]
            except (OSError, ValueError):
                pass
            session.stderr_tail = tail.splitlines()[-40:]

        session.stderr_thread = threading.Thread(target=drain, daemon=True)
        session.stderr_thread.start()
        return session

    def events(self, session: ClaudeCliSession) -> Iterator[HarnessEvent]:
        assert session.process.stdout is not None
        yield HarnessEvent("harness.started", {"harness": "codex-cli", "pid": session.process.pid})
        for raw in session.process.stdout:
            line = raw.strip()
            if not line:
                continue
            session.lines_seen += 1
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                if is_auth_failure(line):
                    session.saw_auth_error = True
                yield HarnessEvent("harness.stdout", {"line": line[:500]})
                continue
            if isinstance(message, dict):
                yield from self._normalize_codex(session, message)
        session.process.wait()
        if session.stderr_thread is not None:
            session.stderr_thread.join(timeout=5)

    def result(self, session: ClaudeCliSession) -> HarnessOutcome:
        exit_code = session.process.poll()
        final = session.result_message or {}
        usage = codex_usage(final, session.started_at)
        if session.cancelled:
            return HarnessOutcome(
                BuildResultStatus.CANCELLED, usage, FailureCategory.CANCELLED, exit_code=exit_code
            )
        error = str(final.get("error") or "")
        stderr = " ".join(session.stderr_tail)
        if session.saw_auth_error or is_auth_failure(error) or is_auth_failure(stderr):
            message = (error or stderr)[:300] or "Codex is not signed in"
            return HarnessOutcome(
                BuildResultStatus.FAILED,
                usage,
                FailureCategory.HARNESS_AUTH,
                [BuildDiagnostic(level="error", code="cli_not_logged_in", message=message)],
                error,
                exit_code,
            )
        if session.lines_seen == 0:
            msg = stderr[:300] or "no output from codex CLI"
            return HarnessOutcome(
                BuildResultStatus.FAILED,
                usage,
                FailureCategory.HARNESS_UNAVAILABLE,
                [BuildDiagnostic(level="error", code="cli_no_output", message=msg)],
                "",
                exit_code,
            )
        if error or final.get("type") != "turn.completed" or exit_code not in (0, None):
            message = error[:300] or f"codex ended without finishing (exit {exit_code})"
            return HarnessOutcome(
                BuildResultStatus.FAILED,
                usage,
                FailureCategory.HARNESS_ERROR,
                [BuildDiagnostic(level="error", code="cli_error", message=message)],
                error,
                exit_code,
            )
        return HarnessOutcome(
            BuildResultStatus.CANDIDATE, usage, None, [], str(final.get("text") or ""), exit_code
        )

    def _normalize_codex(
        self, session: ClaudeCliSession, message: dict[str, Any]
    ) -> Iterator[HarnessEvent]:
        kind = str(message.get("type") or "")
        item = message.get("item") if isinstance(message.get("item"), dict) else None
        final = session.result_message or {}
        if kind == "item.completed" and item is not None:
            item_type = item.get("type")
            if item_type == "agent_message":
                text = str(item.get("text") or "")
                final["text"] = text
                session.result_message = final
                if is_auth_failure(text):
                    session.saw_auth_error = True
                yield HarnessEvent("harness.assistant_text", {"text": text[:2000]})
            elif item_type == "command_execution":
                yield HarnessEvent(
                    "harness.tool_use",
                    {"tool": "Bash", "input": {"command": str(item.get("command") or "")[:200]}},
                )
                yield HarnessEvent(
                    "harness.tool_result",
                    {
                        "is_error": item.get("exit_code") not in (0, None),
                        "preview": str(item.get("aggregated_output") or "")[:300],
                    },
                )
            elif item_type == "file_change":
                for change in item.get("changes") or []:
                    if isinstance(change, dict):
                        yield HarnessEvent(
                            "harness.tool_use",
                            {"tool": "Edit", "input": {"file_path": str(change.get("path"))}},
                        )
        elif kind in ("turn.completed", "turn.failed", "error"):
            err = message.get("error")
            text = (err.get("message") if isinstance(err, dict) else err) or message.get("message")
            final.update({"type": kind, "usage": message.get("usage") or final.get("usage")})
            if kind != "turn.completed":
                final["error"] = str(text or "Codex stopped with an error")
                if is_auth_failure(final["error"]):
                    session.saw_auth_error = True
            session.result_message = final
            yield HarnessEvent("harness.result", {"subtype": kind, "error": final.get("error")})
        elif kind == "thread.started":
            yield HarnessEvent(
                "harness.system", {"subtype": "init", "thread": message.get("thread_id")}
            )


def codex_usage(final: dict[str, Any], started_at: float) -> BuildUsage:
    usage = final.get("usage") if isinstance(final.get("usage"), dict) else {}
    return BuildUsage(
        input_tokens=int(usage.get("input_tokens", 0) or 0),
        output_tokens=int(usage.get("output_tokens", 0) or 0),
        cache_read_input_tokens=int(usage.get("cached_input_tokens", 0) or 0),
        turns=1 if final.get("type") == "turn.completed" else 0,
        duration_ms=int((time.monotonic() - started_at) * 1000),
        cost_basis=CostBasis.SUBSCRIPTION_UNMETERED,
    )
