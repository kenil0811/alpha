"""Project icons, auto-naming from the first message, project files (plan.md), Alpha's own
bug log, and the builder's sign-in refusal."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alpha.api.session_routes import register
from alpha.assistant.acting import fallback_project_name
from alpha.bugs import BugLog
from alpha.builds.harness_claude_cli import is_auth_failure
from alpha.capabilities.errors import OperationFailed
from alpha.context.projects import UNTITLED, ProjectService, brief_markdown
from alpha.solutions.creation import CreationService
from alpha.storage.control_store import ControlStore
from alpha_contracts.briefs import SolutionBrief
from fastapi import FastAPI, HTTPException
from test_planner_coverage import BRIEF
from test_sessions import build


def _endpoint(app: FastAPI, path: str) -> Any:
    return next(r for r in app.routes if getattr(r, "path", None) == path).endpoint


def test_icon_is_stored_and_checked_and_survives_an_old_table(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    store.execute_script(
        "CREATE TABLE projects (project_id TEXT PRIMARY KEY, name TEXT NOT NULL, goal TEXT,"
        " summary TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, archived_at TEXT);"
    )
    projects = ProjectService(store)
    project = projects.create("Trips")
    assert project.icon is None
    assert projects.update(project.project_id, icon="plane").icon == "plane"
    with pytest.raises(OperationFailed):
        projects.update(project.project_id, icon="rocket")


def test_the_first_message_names_an_untitled_project_once(tmp_path: Path) -> None:
    acting, sessions, projects, _profile, _assistant = build(tmp_path)
    project = projects.create(UNTITLED)
    session = sessions.create(project_id=project.project_id)
    acting.send(session.session_id, "plan my sister's wedding budget", wait=True)
    named = projects.get(project.project_id)
    assert named.name == "Plan Sister's Wedding"
    assert named.icon == "folder"
    projects.update(project.project_id, name="Wedding")
    acting.send(session.session_id, "track the caterer quotes", wait=True)
    assert projects.get(project.project_id).name == "Wedding"  # never over the person's name


def test_the_model_name_and_icon_win_and_a_greeting_names_nothing(tmp_path: Path) -> None:
    acting, sessions, projects, _profile, _assistant = build(tmp_path)
    project = projects.create(UNTITLED)
    acting._name_project(project.project_id, "hi", {})
    assert projects.get(project.project_id).name == UNTITLED
    acting._name_project(
        project.project_id, "x", {"project_name": "Wedding Budget", "project_icon": "wallet"}
    )
    assert (projects.get(project.project_id).name, projects.get(project.project_id).icon) == (
        "Wedding Budget",
        "wallet",
    )
    assert fallback_project_name("hello there") is None


def test_brief_markdown_reads_like_the_brief_card() -> None:
    brief = SolutionBrief.model_validate(
        {
            **BRIEF.model_dump(mode="json"),
            "primary_journey": [{"action": "Type what you ate", "expected_result": "It is saved"}],
            "assumptions": [{"text": "Calories are estimates", "source": "model_default"}],
            "unavailable_capabilities": ["messaging"],
        }
    )
    text = brief_markdown(brief, "Stored on this Mac.")
    assert text.startswith("# Track what I eat\n\nEntries and trends are right\n")
    assert "## How you'll use it\n1. Type what you ate: It is saved" in text
    assert "- food entries: food (text)" in text
    assert "- Calories are estimates (default)" in text
    assert "## Not possible yet\n- sending messages" in text
    assert "## Where your data goes\nStored on this Mac." in text
    assert "Not possible yet" not in brief_markdown(BRIEF)


def test_files_route_and_bugs_route(tmp_path: Path) -> None:
    acting, sessions, _projects, _profile, _assistant = build(tmp_path)
    projects = ProjectService(ControlStore(tmp_path / "files.sqlite"), tmp_path / "projects")
    bugs = BugLog(tmp_path / "bugs.md")
    app = FastAPI()
    register(app, projects, sessions, acting, bugs=bugs)
    read_file = _endpoint(app, "/api/projects/{project_id}/files/{name}")
    read_bugs = _endpoint(app, "/api/bugs")
    project = projects.create("Food")
    assert read_file(project.project_id, "plan.md") == {
        "name": "plan.md",
        "text": None,
        "updated_at": None,
    }
    projects.write_file(project.project_id, "plan.md", "# Food\n")
    found = read_file(project.project_id, "plan.md")
    assert found["text"] == "# Food\n" and found["updated_at"]
    with pytest.raises(HTTPException) as unknown:
        read_file("proj_nope", "plan.md")
    assert unknown.value.status_code == 404
    with pytest.raises(HTTPException) as traversal:
        read_file(project.project_id, "../control.sqlite")
    assert traversal.value.status_code == 422
    assert read_bugs() == {"text": None}
    bugs.record("model", "sign_in (cli_not_logged_in)")
    assert "sign_in" in read_bugs()["text"]


def test_bug_log_counts_repeats_and_moves_fixed_entries(tmp_path: Path) -> None:
    log = BugLog(tmp_path / "bugs.md")
    log.record("build", "checking: repair_limit_reached", "the total is wrong")
    log.record("build", "checking: repair_limit_reached", "the total is still wrong")
    log.record("creation", "timeout")
    text = log.read() or ""
    assert "Alpha maintains this file" in text
    assert text.count("checking: repair_limit_reached") == 1
    assert "seen 2 times" in text and "the total is still wrong" in text
    log.resolve("build", "checking: repair_limit_reached")
    text = log.read() or ""
    open_part, fixed_part = text.split("## Fixed")
    assert "repair_limit_reached" in fixed_part and "repair_limit_reached" not in open_part
    assert "[creation] timeout — seen 1 time," in open_part
    log.record("build", "checking: repair_limit_reached")  # it came back
    open_part, fixed_part = (log.read() or "").split("## Fixed")
    assert "seen 3 times" in open_part and "repair_limit_reached" not in fixed_part


def test_a_refused_sign_in_is_an_auth_failure_with_a_connect_step() -> None:
    refused = (
        "Your organization has disabled Claude subscription access for Claude Code · "
        "Use an Anthropic API key instead, or ask your admin to enable access"
    )
    assert is_auth_failure(refused) and is_auth_failure("Not logged in · Please run /login")
    assert not is_auth_failure("Done: the package is ready")
    build = SimpleNamespace(
        terminal_reason="harness_failed",
        failure_category="harness_auth",
        route_id="claude-code-cli",
        validation={"checks": [{"summary": "has no action 'capture_note'", "status": "failed"}]},
        state=None,
        attempts=[1],
    )
    failure = CreationService._build_failure(build)  # type: ignore[arg-type]
    assert failure["next_step"] == "connect"
    assert "Settings → Models" in failure["message"]
    assert failure["failed_checks"] == []
    # The refusal turns the Claude row red until a call works or the person signs in again.
    from alpha.models import accounts

    assert accounts.refused("claude")
    rows = accounts.ModelAccounts()
    assert rows._cached_test("claude")["ok"] is False
    accounts.note_working("claude")
    assert accounts.refused("claude") is None


def test_the_builder_uses_the_same_claude_sign_in_as_the_chat(monkeypatch: Any) -> None:
    from alpha.models import claude_oauth

    monkeypatch.setattr(claude_oauth, "signed_in", lambda: True)
    monkeypatch.setattr(claude_oauth, "access_token", lambda: "tok")
    assert claude_oauth.auth_mode("claude") == "oauth"
    assert claude_oauth.auth_mode("claude_api") == "api_key"
    assert claude_oauth.cli_auth_env("oauth") == {"CLAUDE_CODE_OAUTH_TOKEN": "tok"}
    assert claude_oauth.cli_auth_env("cli") == {}
    monkeypatch.setattr(claude_oauth, "signed_in", lambda: False)
    assert claude_oauth.auth_mode("claude") == "cli"
