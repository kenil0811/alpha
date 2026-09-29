"""Claude Code CLI harness (founder decision 2026-09-25: subscription route, internal use only).

Runs `claude -p` headless in the build workspace with:
- a private config home when it can authenticate, otherwise the user's home with every ambient
  setting source ignored (`--setting-sources ""`), no MCP servers, no session persistence;
- `--restricted`: file tools confined to the workspace, bypass mode refused, code-running tools
  only if named; `--permission-prompts none`: anything that would prompt is denied;
- an explicit tool list and a narrow Bash allowlist: compiling and unit-testing the candidate
  with the App profile's interpreter only (no `python -c`, `ls` or `cat`: those reach any path);
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
import threading
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
from alpha.builds.validate import write_validate_script

PACKAGE_CONTRACT = """You are building an Alpha App: a small tool a nontechnical person will use
to get real work done. Work ONLY inside the current directory.

Edit the App package in package/. It starts from the platform template, from your previous
attempt when REPAIR.md exists, or from the App's current version when the instructions below
say this is a CHANGE to an existing App. Read these files first:
- PLAN.md: the independent checks the platform runs against your package by calling its actions
  for real and reading what was stored. They alone decide success; editing PLAN.md changes nothing.
  Alpha may replace it with a fuller version while you work (the complete checks are written in
  parallel): read PLAN.md again before you finish and satisfy every name, label and case in it.
- REPAIR.md (only on a repair): the checks your previous attempt failed, with the evidence.
- reference/APP_CONTRACT.md: every app.yaml field and rule, including `views` and `screen`.
- reference/SDK.md: the only API your Python may use (ctx.records, ctx.artifacts, ctx.models).

Rules:
- package/app.yaml must keep the exact platform values listed below (app_id included when it
  is listed). Choose name and description yourself, in the person's words.
- Each attempt is stopped after a fixed time (see below). Build what a capable product person
  would expect for this request, complete and usable on the first try: the Python package
  first, then the screen. PLAN.md's checks are the floor, not the ceiling. Every App that
  tracks things gives each table a `detail` (the record's own page: every field, long text
  readable, the actions that apply), shows when entries were added (`created_at`, titled
  "Added") and when each source was last read, offers saved lists over its statuses and
  categories, and summarises what matters. Skip only what the goal does not ask for AND a
  product person would not expect. If time runs short, finish and polish what exists rather
  than starting more.
- Sources named loosely ("LinkedIn", "Indeed") are the App's job to resolve, not the person's:
  keep a small table of known sites and their listing-page address patterns, fall back to
  ctx.web.search to find the listing page, verify it yields item links before saving it, store
  the resolved address next to the name, and tell the person what was found. While you build
  you may use WebFetch and WebSearch to look at the real sites the goal names and write the
  reader for their actual structure (which links are items, where the details live); note what
  you learned in a comment so a later change can follow it.
- Model calls are slow (seconds each): never call ctx.models once per item in a loop. Send one
  structured call for a batch of items (up to ~20, input under 60 KB) asking for a `json` field
  that holds a list with one entry per item (name the keys in the instruction; see SDK.md), and
  score, summarise or extract in that one call.
- Python in package/src/ imports only the standard library, alpha_sdk and the package's own
  modules. No file, socket, subprocess or environment access: data through ctx.records, model
  estimates through ctx.models, and public web pages or search through ctx.web (declare the
  http capability). Keep the address a fact came from next to what you save. To find items on
  a listing page (jobs, products, articles) use page.links (text + absolute url) filtered by
  address pattern, never regexes over page.text; fetch an item's own page for its details, and
  use ctx.models with a schema when items need reading. Never fabricate placeholder items.
  Sites that need a sign-in (LinkedIn, Indeed) are read through the person's own browser
  session when the App declares the browser capability and the person allows it: call
  ctx.web.get as usual, check page.blocked, and never attempt to log in. Pages drawn by
  scripts: ctx.web.get(url, rendered=True).
  While Alpha runs PLAN.md's checks the web is unreachable (every ctx.web call raises): an
  action that reads the web must then report that plainly and store nothing; do not add inputs
  whose only purpose is to stand in for a page's contents.
- The screen is DECLARED in app.yaml under `screen:` (tabs of blocks: quick_entry, table,
  metrics, progress, trend, board, list, form, text) over read views declared under `views:`. Alpha
  draws it. Every action a block runs must list ui in invocable_from. Lay it out by the MODULE
  CONVENTIONS in the instructions below (data first; a quick_entry above it only when typing a
  line is the main way in; forms after; then metrics and trends). Use the labels PLAN.md names
  for placeholders, column titles and tab names. Do not write ui/src/main.tsx.
- Do not write or run your own unit tests, probes or sample scripts: Alpha verifies the package
  against PLAN.md with real runs. Check your own work with `./validate` (run exactly that, from
  the current directory, no cd and no arguments): it applies Alpha's own package rules (app.yaml
  parses and matches the contract, files follow the layout, the Python compiles, every handler
  resolves) and lists what is wrong. Run it after writing app.yaml and the handlers, and again
  before you finish; only hand over a package it reports OK.
- Never add requirements.txt, pyproject.toml, package.json, lock files, .env files, dist/ or
  dependencies/. Extra packages are not available and are never installed.
- Model estimates: store every model result with estimated= so people see it as an estimate.
  If ctx.models.structured raises, never substitute a guess or a default number: save the value
  as unknown (None) and say so, or refuse with a plain message asking the person to type it.
- Actions the person runs from the screen should return a `message` in plain words saying what
  happened; the shell shows it.
- Work that should happen on its own (checking a site every few hours, a nightly summary) is a
  `schedules:` entry in app.yaml running an action that lists trigger in invocable_from, with
  the schedules capability declared. Alpha runs it while it is open.
"""


@dataclass
class ClaudeCliSession:
    session_ref: str
    process: subprocess.Popen[str]
    config_home: Path
    started_at: float
    result_message: dict[str, Any] | None = None
    stderr_tail: list[str] = field(default_factory=list)
    stderr_thread: threading.Thread | None = None
    cancelled: bool = False
    saw_auth_error: bool = False
    lines_seen: int = 0


class ClaudeCliHarness:
    def __init__(
        self,
        *,
        claude_binary: str | None = None,
        candidate_python: Path | None = None,
        config_home_strategy: str = "user_default_settings_ignored",
    ) -> None:
        self._binary = claude_binary or shutil.which("claude") or "claude"
        self._python = candidate_python or Path(sys.executable)
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
        validate = write_validate_script(workspace, self._python)
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
            "Read,Write,Edit,Glob,Grep,Bash,WebFetch,WebSearch",
            "--allowedTools",
            # Reading goes through Read/Glob/Grep, which --restricted confines to the workspace.
            # Only the candidate's own compile and unit-test commands may run, on the App
            # profile's interpreter. (Unit tests still run builder-written code unsandboxed
            # until F20 qualifies the OS sandbox.) The public web is readable so the builder
            # can look at the sites the goal names and write a reader for their real structure.
            f"Bash({self._python} -m py_compile:*)",
            f"Bash({self._python} -m unittest:*)",
            # The attempt's own validate script: Alpha's package rules, read-only.
            f"Bash(./{validate.name}:*)",
            f"Bash({validate}:*)",
            "WebFetch",
            "WebSearch",
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
        session = ClaudeCliSession(
            session_ref=f"claude-cli-{process.pid}",
            process=process,
            config_home=config_home,
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
        if session.stderr_thread is not None:
            session.stderr_thread.join(timeout=5)

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
        exact = "\n".join(f"- {key}: {value}" for key, value in sorted(inputs.targets.items()))
        ui_note = (
            "Custom compiled screens are allowed on this build: if, and only if, no declared "
            "block can express the main interaction, you may instead write ui/src/main.tsx "
            "(see reference/UI_KIT.md) and declare ui.entry with ui.build_profile, "
            "ui.kit_version and ui.bridge_version as above. A declared screen is still preferred."
            if "ui_build_profile" in inputs.targets
            else "Custom compiled screens are not available on this build: declare the screen "
            "under screen: and leave ui out of app.yaml."
        )
        repair = (inputs.workspace / "REPAIR.md").is_file()
        minutes = max(1, inputs.request.budget.max_attempt_seconds // 60)
        return (
            f"{PACKAGE_CONTRACT}\nPlatform interpreter: {self._python}\n"
            f"Time for this attempt: {minutes} minutes.\n\n"
            f"Exact platform values for app.yaml:\n{exact}\n{ui_note}\n\n"
            f"GOAL (from the person, plain language):\n{inputs.goal}\n\n"
            f"ADDITIONAL INSTRUCTIONS:\n{inputs.instructions or '(none)'}\n\n"
            + (
                "This is a REPAIR attempt: start by reading REPAIR.md, then fix package/.\n"
                if repair
                else "Start by reading PLAN.md and the reference/ files.\n"
            )
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
