"""Is Alpha's route to Claude working, and if not, why?

Alpha reaches Claude only through the local `claude` CLI and the person's own login. This
monitor answers from the same binary, PATH and cleared environment the model calls use: is the
CLI there, does it understand every flag Alpha passes, is it signed in, and did the last real
call work. It can run a tiny real call on request and start `claude auth login` (the CLI opens
the browser and finishes through its own localhost callback). Nothing here reads, logs or
returns a credential: `claude auth status --json` reports only who is signed in.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from dataclasses import replace
from typing import Any

from alpha.models.gateway import ModelGateway, RouteUnavailable
from alpha.models.structured import InferenceError, StructuredInference
from alpha.storage.control_store import ControlStore, utc_now

ROUTE_ID = "claude-code-cli"
# Every flag Alpha passes to the CLI (models/structured.py, builds/harness_claude_cli.py) that
# `claude --help` lists. A CLI missing any of them refuses the call ("unknown option"), so the
# decisive "too old" test is this list, not a version number. tests/test_model_connection.py
# keeps it in step with the call sites.
REQUIRED_FLAGS: tuple[str, ...] = (
    "--allowedTools",
    "--json-schema",
    "--max-budget-usd",
    "--model",
    "--no-session-persistence",
    "--output-format",
    "--permission-mode",
    "--permission-prompts",
    "--restricted",
    "--setting-sources",
    "--strict-mcp-config",
    "--system-prompt",
    "--tools",
    "--verbose",
)
# Passed too, but not listed by `--help`.
UNLISTED_FLAGS: tuple[str, ...] = ("--max-turns", "--version")
# The oldest version known to take every flag above (2.1.223 lacks --permission-prompts and
# --restricted; measured 27 September 2026).
MIN_SUPPORTED_VERSION = "2.1.283"
PROBE_SECONDS = 20
CHECK_SECONDS = 60
LOGIN_SECONDS = 300
LOGIN_POLL_SECONDS = 2.0

_FIX = {
    "cli_missing": "Install Claude Code (https://claude.com/claude-code), sign in once, then "
    "press Check now.",
    "cli_too_old": "Update Claude Code: run `claude update` in Terminal, then press Check now.",
    "signed_out": "Sign in to Claude Code: press Sign in, or run `claude auth login` in Terminal.",
    "last_call_failed": "Press Check now to try a small call. If it keeps failing, see the "
    "reason above.",
}


def _now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def _version_key(text: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", text)[:3])


def missing_flags(help_text: str) -> list[str]:
    return [
        f for f in REQUIRED_FLAGS if not re.search(rf"(?<![\w-]){re.escape(f)}(?![\w-])", help_text)
    ]


class ConnectionMonitor:
    def __init__(
        self, store: ControlStore, gateway: ModelGateway, inference: StructuredInference
    ) -> None:
        self._store = store
        self._gateway = gateway
        self._inference = inference
        self._lock = threading.Lock()
        # (path, mtime) -> (version, missing flags): the binary changes only when it is updated.
        self._probe_cache: dict[tuple[str, float], tuple[str | None, list[str]]] = {}
        self._login: subprocess.Popen[bytes] | None = None
        self._login_state: dict[str, Any] | None = None

    # ----- reading -------------------------------------------------------------------------

    def _route_enabled(self) -> bool:
        try:
            self._gateway.route(ROUTE_ID)
        except RouteUnavailable:
            return False
        return True

    def _run(self, path: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [path, *args],
            capture_output=True,
            text=True,
            env=self._inference.cli_env(),
            stdin=subprocess.DEVNULL,
            timeout=PROBE_SECONDS,
        )

    def _probe(self, path: str) -> tuple[str | None, list[str]]:
        key = (os.path.realpath(path), os.stat(path).st_mtime)
        cached = self._probe_cache.get(key)
        if cached is not None:
            return cached
        version: str | None = None
        try:
            out = self._run(path, "--version").stdout.strip()
            version = out.split()[0] if out else None
            help_text = self._run(path, "--help").stdout
        except (OSError, subprocess.TimeoutExpired):
            return None, []
        result = (version, missing_flags(help_text))
        self._probe_cache = {key: result}
        return result

    def _auth(self, path: str) -> tuple[bool | None, dict[str, Any] | None]:
        """Signed in or not, and who: only the fields the page shows, never a token."""
        try:
            out = self._run(path, "auth", "status", "--json").stdout
            status = json.loads(out[out.index("{") :])
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return None, None
        if not isinstance(status, dict):
            return None, None
        logged_in = bool(status.get("loggedIn"))
        if not logged_in:
            return False, None
        return True, {
            "auth_method": status.get("authMethod"),
            "email": status.get("email"),
            "organization": status.get("orgName"),
            "plan": status.get("subscriptionType"),
        }

    def _last_success(self) -> tuple[str | None, int | None]:
        """The newest call that worked: this session's (every stage) or a module's recorded one."""
        found: list[tuple[str, int | None]] = []
        if self._inference.last_success:
            ok = self._inference.last_success
            found.append((str(ok["at"]), ok.get("elapsed_ms")))
        found += [(r["created_at"], r["elapsed_ms"]) for r in self._model_calls("ok")]
        return max(found, key=lambda f: f[0]) if found else (None, None)

    def _model_calls(self, status: str) -> list[Any]:
        try:
            return self._store.query(
                "SELECT error, elapsed_ms, created_at FROM model_calls"
                " WHERE route_id = ? AND status = ? ORDER BY created_at DESC LIMIT 1",
                (ROUTE_ID, status),
            )
        except Exception:  # model_calls exists only once App runs are set up
            return []

    def _last_failure(self) -> dict[str, str] | None:
        """The newest failed call: this session's (every stage) or a module's recorded one."""
        failures = [self._inference.last_failure] if self._inference.last_failure else []
        for row in self._model_calls("failed"):
            code, _, message = str(row["error"] or "").partition(": ")
            failures.append({"code": code, "message": message or code, "at": row["created_at"]})
        return max(failures, key=lambda f: f["at"]) if failures else None

    def snapshot(self) -> dict[str, Any]:
        enabled = self._route_enabled()
        path = self._inference.cli_path()
        version, missing = self._probe(path) if path else (None, [])
        logged_in, account = self._auth(path) if path and not missing else (None, None)
        last_ok, latency = self._last_success()
        failure = self._last_failure()
        if failure and last_ok and failure["at"] <= last_ok:
            failure = None
        if not enabled:
            status = "not_used"
        elif path is None:
            status = "cli_missing"
        elif missing:
            status = "cli_too_old"
        elif logged_in is False:
            status = "signed_out"
        elif failure is not None:
            status = "last_call_failed"
        else:
            status = "connected"
        with self._lock:
            login = dict(self._login_state) if self._login_state else None
        return {
            "route_enabled": enabled,
            "status": status,
            "fix": _FIX.get(status),
            "cli_found": path is not None,
            "cli_path": path,
            "cli_version": version,
            "min_supported_version": MIN_SUPPORTED_VERSION,
            "version_supported": version is not None
            and _version_key(version) >= _version_key(MIN_SUPPORTED_VERSION),
            "missing_flags": missing,
            "logged_in": logged_in,
            "account": account,
            "last_successful_call_at": last_ok,
            "last_call_latency_ms": latency,
            "last_error": failure,
            "login": login,
            "checked_at": _now(),
        }

    # ----- acting ----------------------------------------------------------------------------

    def check(self) -> dict[str, Any]:
        """One tiny real call on the fastest model; its outcome is what the snapshot then shows."""
        outcome: dict[str, Any]
        if not self._route_enabled():
            outcome = {"ok": False, "error": "Claude Code is not used on this host."}
        else:
            route = replace(self._gateway.route(ROUTE_ID), model="haiku")
            started = time.monotonic()
            try:
                self._inference.call(
                    route,
                    system="Answer with ok set to true.",
                    prompt="Are you there?",
                    schema={
                        "type": "object",
                        "properties": {"ok": {"type": "boolean"}},
                        "required": ["ok"],
                    },
                    scope_kind="connection_check",
                    scope_ref="connection_check",
                    timeout_seconds=CHECK_SECONDS,
                )
                outcome = {"ok": True, "elapsed_ms": int((time.monotonic() - started) * 1000)}
            except InferenceError as exc:
                outcome = {"ok": False, "code": exc.code, "error": str(exc)[:300]}
        return {**self.snapshot(), "check": outcome}

    def login(self) -> dict[str, Any]:
        """Start `claude auth login` (it opens the browser) under supervision: stopped once the
        CLI reports signed in, or after five minutes. A second press while one runs is a no-op."""
        path = self._inference.cli_path()
        if path is None:
            raise LoginUnavailable("Claude Code is not installed on this Mac.")
        proc: subprocess.Popen[bytes] | None
        with self._lock:
            if self._login is not None and self._login.poll() is None:
                proc = None
            else:
                proc = self._start_login(path)
        if proc is not None:
            threading.Thread(target=self._supervise, args=(proc, path), daemon=True).start()
        return self.snapshot()

    def _start_login(self, path: str) -> subprocess.Popen[bytes]:
        self._login = subprocess.Popen(
            [path, "auth", "login", "--claudeai"],
            env=self._inference.cli_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._login_state = {"state": "waiting", "started_at": _now()}
        return self._login

    def _supervise(self, proc: subprocess.Popen[bytes], path: str) -> None:
        deadline = time.monotonic() + LOGIN_SECONDS
        signed_in = False
        while time.monotonic() < deadline:
            signed_in = self._auth(path)[0] is True
            if signed_in or proc.poll() is not None:
                break
            time.sleep(LOGIN_POLL_SECONDS)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if not signed_in:
            signed_in = self._auth(path)[0] is True
        state = (
            "signed_in"
            if signed_in
            else ("timed_out" if time.monotonic() >= deadline else "not_completed")
        )
        with self._lock:
            if self._login is proc and self._login_state is not None:
                self._login_state = {**self._login_state, "state": state, "finished_at": _now()}


class LoginUnavailable(Exception):
    pass
