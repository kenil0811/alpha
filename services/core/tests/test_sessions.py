"""Projects and sessions: durable chats with memory, cards for the work they start, verbatim
search across sessions, and compaction that folds old turns into notes and suggests facts."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alpha.assistant.acting import ActService
from alpha.assistant.sessions import COMPACT_AT, WINDOW_TURNS, SessionService
from alpha.capabilities.errors import OperationFailed
from alpha.context.pack import ContextPacker
from alpha.context.profile import ProfileService, project_scope
from alpha.context.projects import ProjectService
from alpha.models.gateway import ModelGateway
from alpha.models.structured import StructuredInference
from alpha.storage.control_store import ControlStore
from test_acting import Records, Registry, Runs  # noqa: I001


class Assistant:
    """Enough of the assistant for the loop: conversations start, and can wait on the person."""

    def __init__(self) -> None:
        self.started: list[tuple[str, str | None, str | None]] = []
        self.replies: list[tuple[str, str]] = []
        self.states: dict[str, str] = {}

    def start(
        self, text: str, *, change_of: str | None = None, session_id: str | None = None
    ) -> Any:
        conversation_id = f"conv_{len(self.started) + 1}"
        self.started.append((text, change_of, session_id))
        self.states[conversation_id] = "waiting_for_user"
        return SimpleNamespace(conversation_id=conversation_id)

    def reply(self, conversation_id: str, *, text: str) -> Any:
        self.replies.append((conversation_id, text))
        self.states[conversation_id] = "briefed"
        return SimpleNamespace(conversation_id=conversation_id)

    def get(self, conversation_id: str) -> Any:
        return SimpleNamespace(state=self.states.get(conversation_id, "answered"))


Built = tuple[ActService, SessionService, ProjectService, ProfileService, Assistant]


def build(tmp_path: Path) -> Built:
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(store, frozenset({"fake"}))
    inference = StructuredInference(gateway)
    profile = ProfileService(store)
    projects = ProjectService(store)
    sessions = SessionService(
        store, gateway=gateway, inference=inference, profile=profile, projects=projects
    )
    assistant = Assistant()
    runs = Runs()
    acting = ActService(
        store,
        gateway,
        inference,
        registry=Registry(),
        runs=runs,
        records=Records(),
        assistant=assistant,
        sessions=sessions,
        default_route="fake",
        run_lookup=runs.lookup,
        today=lambda: "2026-09-29",
        projects=projects,
        context=ContextPacker(profile, Registry(), Records(), store, projects=projects).build,
    )
    return acting, sessions, projects, profile, assistant


def test_projects_group_modules_and_a_module_is_in_one_project(tmp_path: Path) -> None:
    _, _, projects, _, _ = build(tmp_path)
    hunt = projects.create("Job hunt", goal="A backend role in London by December")
    health = projects.create("Health")
    projects.file_module("notes", hunt.project_id)
    assert projects.project_of("notes") == hunt.project_id
    projects.file_module("notes", health.project_id)
    assert projects.get(hunt.project_id).modules == []
    assert projects.get(health.project_id).modules == ["notes"]
    projects.file_module("notes", None)
    assert projects.project_of("notes") is None
    with pytest.raises(OperationFailed):
        projects.file_module("notes", "proj_missing")
    projects.update(hunt.project_id, archived=True)
    assert [p.name for p in projects.list_projects()] == ["Health"]


def test_a_session_keeps_every_turn_and_names_itself(tmp_path: Path) -> None:
    acting, sessions, _, _, _ = build(tmp_path)
    session = sessions.create()
    turn = acting.send(session.session_id, "hello there", wait=True)
    assert turn is not None and turn.kind == "answer"
    after = sessions.get(session.session_id)
    assert [t.role for t in after.turns] == ["user", "alpha"]
    assert after.title == "hello there" and after.state == "idle" and after.turn_count == 2
    assert after.turns[1].outcome == "nothing was done; Alpha only replied"


def test_a_build_becomes_a_card_and_text_goes_to_a_waiting_conversation(tmp_path: Path) -> None:
    acting, sessions, _, _, assistant = build(tmp_path)
    session = sessions.create()
    turn = acting.send(session.session_id, "fake:build a reading list", wait=True)
    assert turn is not None and turn.kind == "build" and turn.conversation_id == "conv_1"
    assert assistant.started == [("fake:build a reading list", None, session.session_id)]
    card = sessions.get(session.session_id).turns[-1]
    assert card.kind == "work" and card.conversation_id == "conv_1"
    assert card.outcome and "waiting for the person's answers" in card.outcome
    # The conversation is waiting: the next message answers it instead of starting anew.
    follow = acting.send(session.session_id, "paperbacks only", wait=True)
    assert follow is not None and follow.kind == "continue"
    assert assistant.replies == [("conv_1", "paperbacks only")]
    assert len(assistant.started) == 1
    # Once it is briefed, messages go through the loop again.
    plain = acting.send(session.session_id, "thanks", wait=True)
    assert plain is not None and plain.kind == "answer"


def test_a_session_refuses_a_second_message_while_thinking(tmp_path: Path) -> None:
    acting, sessions, _, _, _ = build(tmp_path)
    session = sessions.create()
    sessions.begin_turn(session.session_id)
    with pytest.raises(OperationFailed) as failed:
        acting.send(session.session_id, "again", wait=True)
    assert failed.value.code == "conflict"
    sessions.set_state(session.session_id, "idle")
    assert sessions.reconcile_on_startup() == []


def test_memory_carries_notes_recent_turns_and_matching_turns_from_other_sessions(
    tmp_path: Path,
) -> None:
    acting, sessions, projects, _, _ = build(tmp_path)
    hunt = projects.create("Job hunt")
    earlier = sessions.create(project_id=hunt.project_id)
    acting.send(earlier.session_id, "the recruiter at Monzo is called Priya", wait=True)
    other_project = sessions.create(project_id=projects.create("Health").project_id)
    acting.send(other_project.session_id, "Priya recommended a physio", wait=True)
    later = sessions.create(project_id=hunt.project_id)
    acting.send(later.session_id, "fake:open notes", wait=True)
    memory = sessions.memory_text(later.session_id, "what was the recruiter called?")
    assert "person: fake:open notes" in memory, "this session's own turns"
    assert "recruiter at Monzo is called Priya" in memory, "verbatim from the project's session"
    assert "physio" not in memory, "another project's sessions stay out of a project session"
    hits = sessions.search("Priya", scope="all")
    assert {h["session_id"] for h in hits} == {earlier.session_id, other_project.session_id}


def test_compaction_folds_old_turns_into_notes_project_notes_and_suggested_facts(
    tmp_path: Path,
) -> None:
    acting, sessions, projects, profile, _ = build(tmp_path)
    hunt = projects.create("Job hunt", goal="Backend role")
    session = sessions.create(project_id=hunt.project_id)
    for i in range(COMPACT_AT // 2):
        text = f"fact:target_roles=backend turn {i}" if i == 0 else f"plain turn {i}"
        acting.send(session.session_id, text, wait=True)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and sessions.get(session.session_id).summary is None:
        time.sleep(0.05)
    after = sessions.get(session.session_id)
    assert after.summary and after.summary.startswith("Folded")
    assert len(after.turns) == WINDOW_TURNS, "the window stays verbatim; the rest is in the notes"
    assert after.turn_count == COMPACT_AT
    assert projects.get(hunt.project_id).summary == "Project notes after 6 turn(s)."
    suggested = profile.suggestions()
    assert [(f.field, f.value, f.state) for f in suggested] == [
        ("target_roles", "backend", "suggested")
    ]
    assert suggested[0].source == session.session_id and suggested[0].provenance == "assistant"
    # Search still finds a folded turn: the turns are kept, only the prompt window moves.
    assert sessions.search("plain turn 2", scope="project", project_id=hunt.project_id)


def test_project_facts_live_in_their_own_scope(tmp_path: Path) -> None:
    _, _, projects, profile, _ = build(tmp_path)
    hunt = projects.create("Job hunt")
    profile.claim("location", "London", provenance="person", source="person", accepted=True)
    profile.claim(
        "location",
        "remote only",
        provenance="person",
        source="person",
        accepted=True,
        scope=project_scope(hunt.project_id),
    )
    assert profile.get("location").value == "London"
    assert profile.get("location", project_scope(hunt.project_id)).value == "remote only"
    assert profile.as_text(project_scope(hunt.project_id)) == (
        "- location: remote only (they said so)"
    )


def test_the_quick_asks_session_is_the_avatars_and_imports_earlier_turns(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    store.execute_script(
        """CREATE TABLE act_turns (turn_id TEXT PRIMARY KEY, text TEXT NOT NULL, kind TEXT NOT NULL,
           app_id TEXT, action_id TEXT, run_id TEXT, conversation_id TEXT, reply TEXT NOT NULL,
           detail_json TEXT NOT NULL, created_at TEXT NOT NULL);
           INSERT INTO act_turns VALUES ('act_1', 'log two eggs', 'run', 'diet', 'log', 'run_1',
           NULL, 'Logged.', '{"observations": [], "open": null}', '2026-09-28T10:00:00Z');"""
    )
    sessions = SessionService(store)
    quick = sessions.quick_asks()
    assert quick.title == "Quick asks" and quick.origin == "avatar"
    assert [t.text for t in quick.turns] == ["log two eggs", "Logged."]
    assert quick.turns[1].kind == "work" and quick.turns[1].detail["app_id"] == "diet"
    assert sessions.quick_asks().session_id == quick.session_id
    assert store.query("SELECT COUNT(*) AS n FROM act_turns")[0]["n"] == 0


def test_sessions_list_by_scope_and_latest_prefers_the_shell(tmp_path: Path) -> None:
    _, sessions, projects, _, _ = build(tmp_path)
    hunt = projects.create("Job hunt")
    a = sessions.create(project_id=hunt.project_id)
    b = sessions.create()
    sessions.quick_asks()
    # A module outside any project has sessions of its own; Home does not show them.
    m = sessions.create(focus_app_id="notes")
    assert [s.session_id for s in sessions.list_sessions(scope="module", focus_app_id="notes")] == [
        m.session_id
    ]
    assert m.session_id not in {s.session_id for s in sessions.list_sessions(scope="global")}
    assert sessions.latest(project_id=None, focus_app_id="notes").session_id == m.session_id
    global_ids = {s.session_id for s in sessions.list_sessions(scope="global")}
    assert b.session_id in global_ids and a.session_id not in global_ids
    assert sessions.latest(project_id=hunt.project_id).session_id == a.session_id
    latest = sessions.latest(project_id=None)
    assert latest is not None and latest.session_id == b.session_id, "not the avatar's"
    sessions.update(b.session_id, archived=True)
    assert sessions.latest(project_id=None) is None
    with pytest.raises(OperationFailed):
        sessions.create(project_id="proj_missing")
