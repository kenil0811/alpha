"""A request's model choice (the + menu's picker) carries through everything it starts: the
session's later messages, the conversation's replies, its planner and its build. Found 1 October:
ChatGPT was chosen, but only the first call used it; every later stage fell back to Claude."""

from __future__ import annotations

import json
import stat
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from alpha.assistant.service import AssistantService
from alpha.builds.harness import HarnessInputs
from alpha.builds.harness_codex_cli import CodexCliHarness
from alpha.builds.service import BuildPipeline, BuildService
from alpha.builds.store import AcceptanceExample, plan_from_examples
from alpha.execution.supervisor import WorkerSupervisor
from alpha.models.accounts import ModelAccounts
from alpha.models.gateway import ACCOUNT_TO_ROUTE_ID, ModelGateway, RouteUnavailable
from alpha.models.preferences import Preferences
from alpha.solutions.creation import CreationRoutes, CreationService
from alpha.solutions.planner import AcceptancePlan
from alpha.storage.control_store import ControlStore
from alpha_contracts.builds import BuildResultStatus
from test_creation_cancel import BRIEF, PLAN, Builds
from test_sessions import Assistant, build

ROUTES = frozenset({"fake", "claude-code-cli", "chatgpt-codex-cli", "chatgpt-api"})
CHATGPT = {"provider": "chatgpt"}


def gateway(tmp_path: Path) -> tuple[ControlStore, ModelGateway, Preferences]:
    store = ControlStore(tmp_path / "control.sqlite")
    prefs = Preferences(store)  # models.provider unset: every stage defaults to Claude
    return store, ModelGateway(store, ROUTES, preferences=prefs), prefs


def test_a_conversation_started_on_chatgpt_replies_plans_and_builds_on_codex(
    tmp_path: Path,
) -> None:
    store, gw, prefs = gateway(tmp_path)
    prefs.update({"models.codex_model": "gpt-5.5"})
    assistant = AssistantService(store, gw, cast(Any, None), default_route="claude-code-cli")
    turns: list[Any] = []
    assistant._spawn_turn = lambda _cid, route, _latest: turns.append(route)  # type: ignore[method-assign]

    record = assistant.start("track my job applications", model=CHATGPT)
    assert record.model == CHATGPT and record.route_id == "chatgpt-codex-cli"
    with store.transaction() as conn:
        conn.execute("UPDATE conversations SET state = 'waiting_for_user'")
    assistant.reply(record.conversation_id, text="the ones from LinkedIn")  # the reply route
    assert [r.route_id for r in turns] == ["chatgpt-codex-cli", "chatgpt-codex-cli"]
    assert turns[0].model == "gpt-5.5", "the codex route runs the model chosen for it"

    # The creation reads the choice back from the conversation (survives a restart with it).
    planned: list[Any] = []
    submitted: dict[str, Any] = {}

    class Planner:
        def plan(self, _brief: Any, route: Any, *_a: Any, **_k: Any) -> AcceptancePlan:
            planned.append(route)
            return AcceptancePlan("Notes list", PLAN, "model", [])

    class RecordingBuilds(Builds):
        def submit(self, **kwargs: Any) -> Any:
            submitted.update(kwargs)
            return SimpleNamespace(build_id="build_1")

    briefed = SimpleNamespace(
        get=lambda cid: SimpleNamespace(
            state="briefed",
            current_brief=BRIEF,
            quick_change=False,
            change_of=None,
            model=assistant.get(cid).model,
        )
    )
    creations = CreationService(
        store,
        briefed,  # type: ignore[arg-type]
        RecordingBuilds(),  # type: ignore[arg-type]
        Planner(),  # type: ignore[arg-type]
        gw,
        CreationRoutes(planner="claude-code-cli", builder="claude-code-cli"),
        poll_seconds=0.01,
    )
    creation = creations.start(record.conversation_id)
    deadline = time.monotonic() + 5
    while not planned and time.monotonic() < deadline:
        time.sleep(0.01)
    for thread in threading.enumerate():
        if thread.name == f"creation-{creation.creation_id}":
            thread.join(timeout=10)
    assert [r.route_id for r in planned] == ["chatgpt-codex-cli"]
    assert submitted["model"] == CHATGPT

    # ...and the build service resolves that to the Codex builder.
    builds = BuildService(
        store,
        WorkerSupervisor(Path(sys.executable), tmp_path / "scratch", 1.0),
        gw,
        cast(BuildPipeline, None),
        builds_root=tmp_path / "builds",
        builder_path="/usr/bin:/bin",
        builder_home=None,
        instance_id="core_test",
    )
    builds._run_build = lambda _item: None  # type: ignore[method-assign]
    plan = plan_from_examples([AcceptanceExample(action_id="a", input={}, expected={})])
    made = builds.submit(goal="one", plan=plan, route_id="claude-code-cli", model=CHATGPT)
    assert (made.route_id, made.harness) == ("chatgpt-codex-cli", "codex-cli")
    with pytest.raises(RouteUnavailable, match="can't build projects"):
        builds.submit(
            goal="two", plan=plan, route_id="claude-code-cli", model={"provider": "chatgpt_api"}
        )
    builds.shutdown()


def test_without_a_choice_settings_still_decide(tmp_path: Path) -> None:
    store, gw, prefs = gateway(tmp_path)
    assistant = AssistantService(store, gw, cast(Any, None), default_route="claude-code-cli")
    assistant._spawn_turn = lambda *_a: None  # type: ignore[method-assign]
    assert assistant.start("hello").route_id == "claude-code-cli"
    prefs.update({"models.provider": "chatgpt_codex"})
    assert assistant.start("hello").route_id == "chatgpt-codex-cli"


class ModelAssistant(Assistant):
    def __init__(self) -> None:
        super().__init__()
        self.models: list[Any] = []

    def start(self, text: str, **kwargs: Any) -> Any:
        self.models.append(kwargs.pop("model", None))
        return super().start(text, **kwargs)

    def reply(self, conversation_id: str, *, text: str, **kwargs: Any) -> Any:
        self.models.append(kwargs.get("model"))
        return super().reply(conversation_id, text=text)


def test_the_session_keeps_the_choice_for_its_later_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(ACCOUNT_TO_ROUTE_ID, "fake", "fake")  # a pickable account for the test
    acting, sessions, _projects, _profile, _ = build(tmp_path)
    assistant = ModelAssistant()
    acting._assistant = assistant
    session = sessions.create()
    first = acting.send(
        session.session_id, "fake:build a reading list", wait=True, model={"provider": "fake"}
    )
    assert first is not None and first.kind == "build"
    assert sessions.get(session.session_id).model == {"provider": "fake"}
    follow = acting.send(session.session_id, "paperbacks only", wait=True)  # no choice made
    assert follow is not None and follow.kind == "continue"
    # The conversation it opened, and the reply to it, both carry the session's choice.
    assert assistant.models == [{"provider": "fake", "model": None}] * 2


# ----- Settings -> Models: models per provider, the default row ------------------------------


def test_models_per_provider_and_the_default_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    prefs = Preferences(store)
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "models_cache.json").write_text(
        json.dumps(
            {
                "models": [
                    {"slug": "b", "display_name": "B", "visibility": "list", "priority": 2},
                    {"slug": "a", "display_name": "A", "visibility": "list", "priority": 1},
                    {"slug": "h", "display_name": "H", "visibility": "hide", "priority": 0},
                ]
            }
        )
    )
    accounts = ModelAccounts(prefs, tool_path="/usr/bin:/bin", home=str(home))
    monkeypatch.setattr(accounts, "_describe", lambda pid: {"id": pid})
    rows = {r["id"]: r["default"] for r in accounts.list_providers()}
    assert [k for k, v in rows.items() if v] == ["claude"], "Claude when nothing is chosen"
    prefs.update({"models.provider": "chatgpt_codex"})
    assert [r["id"] for r in accounts.list_providers() if r["default"]] == ["chatgpt"]

    claude = accounts.models("claude")
    assert [m["id"] for m in claude["models"]] == ["opus", "sonnet", "haiku"]
    assert claude["selected"] is None
    assert accounts.select_model("claude", "opus")["selected"] == "opus"

    assert accounts.models("chatgpt") == {
        "models": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        "selected": None,
    }
    assert accounts.select_model("chatgpt", "b")["selected"] == "b"

    fetched: list[tuple[str, Any]] = []

    def fake_list(base_url: str, key: Any, timeout: int = 5) -> list[dict[str, Any]]:
        fetched.append((base_url, key))
        return [{"id": "z/model", "name": "Zed"}, {"id": "a/model"}]

    monkeypatch.setattr("alpha.models.accounts.list_models", fake_list)
    monkeypatch.setattr("alpha.models.accounts.keychain.get_key", lambda _p: None)
    assert accounts.models("grok") == {"models": [], "selected": "grok-4"}, "no key: empty"
    first = accounts.models("openrouter")  # public list, no key needed
    assert first["models"] == [
        {"id": "a/model", "label": "a/model"},
        {"id": "z/model", "label": "Zed"},
    ]
    accounts.models("openrouter")
    assert len(fetched) == 1, "cached"

    def broken(*_a: Any, **_k: Any) -> Any:
        from alpha.models.providers import ProviderHTTPError

        raise ProviderHTTPError("offline")

    monkeypatch.setattr("alpha.models.accounts.list_models", broken)
    monkeypatch.setattr("alpha.models.accounts.keychain.get_key", lambda _p: "sk-test")
    assert accounts.models("chatgpt_api")["models"] == [], "a failure is an empty list"


def test_model_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from alpha.api.models_routes import register
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    prefs = Preferences(ControlStore(tmp_path / "control.sqlite"))
    accounts = ModelAccounts(prefs, tool_path="/usr/bin:/bin", home=str(tmp_path))
    monkeypatch.setattr("alpha.models.accounts.keychain.get_key", lambda _p: None)
    app = FastAPI()
    register(app, accounts)
    client = TestClient(app)
    got = client.get("/api/model-accounts/claude/models").json()
    assert got["selected"] is None and got["models"][0] == {"id": "opus", "label": "Claude Opus"}
    put = client.put("/api/model-accounts/claude/model", json={"model": "haiku"})
    assert put.status_code == 200 and put.json()["selected"] == "haiku"
    assert client.put("/api/model-accounts/claude/model", json={"model": "gpt"}).status_code == 400
    assert client.get("/api/model-accounts/nope/models").status_code == 404
    assert client.get("/api/model-accounts/grok/models").json() == {
        "models": [],
        "selected": "grok-4",
    }


# ----- the Codex build harness ----------------------------------------------------------------

CODEX_EVENTS = [
    {"type": "thread.started", "thread_id": "t1"},
    {
        "type": "item.completed",
        "item": {"type": "command_execution", "command": "./validate", "exit_code": 0},
    },
    {"type": "item.completed", "item": {"type": "agent_message", "text": "done"}},
    {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 3}},
]
FAKE_CODEX = '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$(dirname "$0")/argv"\n' + "".join(
    f"echo '{json.dumps(e)}'\n" for e in CODEX_EVENTS
)


def test_the_codex_harness_builds_in_its_sandbox_on_the_chosen_model(tmp_path: Path) -> None:
    binary = tmp_path / "codex"
    binary.write_text(FAKE_CODEX, encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    harness = CodexCliHarness(codex_binary=str(binary), candidate_python=Path(sys.executable))
    inputs = HarnessInputs(
        request=SimpleNamespace(budget=SimpleNamespace(max_attempt_seconds=600)),  # type: ignore[arg-type]
        workspace=workspace,
        goal="notes",
        instructions="",
        model="gpt-5.5",
        candidate_python=Path(sys.executable),
    )
    session = harness.start(inputs)
    kinds = [e.kind for e in harness.events(session)]
    outcome = harness.result(session)
    argv = (tmp_path / "argv").read_text().split("\n")
    assert argv[argv.index("--sandbox") + 1] == "workspace-write"
    assert argv[argv.index("--model") + 1] == "gpt-5.5"
    assert "harness.tool_use" in kinds and "harness.result" in kinds
    assert outcome.status is BuildResultStatus.CANDIDATE
    assert outcome.usage is not None and outcome.usage.input_tokens == 10


def test_one_claude_model_from_the_row_wins_over_each_stage(tmp_path: Path) -> None:
    _store, gw, prefs = gateway(tmp_path)
    assert gw.route("claude-code-cli", "assistant").model == "sonnet"  # the stage's own
    prefs.update({"models.claude_model": "opus"})
    assert gw.route("claude-code-cli", "assistant").model == "opus"
    assert gw.route("claude-code-cli", "builder_new").model == "opus"
