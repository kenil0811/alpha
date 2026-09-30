"""Projects and sessions: the shell's way to group modules around a goal and to talk to Alpha in
durable, resumable chats. Every message goes through the one loop (`ActService.send`)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from alpha.assistant.acting import ActService
from alpha.assistant.attachments import MAX_ATTACHMENTS, AttachmentIn
from alpha.assistant.sessions import Session, SessionService, SessionSummary
from alpha.capabilities.errors import HTTP_STATUS, OperationFailed
from alpha.context.profile import ProfileService, project_scope
from alpha.context.projects import Project, ProjectService
from alpha.models.gateway import RouteUnavailable


class ProjectDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    goal: str | None = Field(default=None, max_length=600)


class ProjectPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    goal: str | None = Field(default=None, max_length=600)
    summary: str | None = Field(default=None, max_length=4000)
    archived: bool | None = None


class FileModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Null to take the module out of every project.
    project_id: str | None = Field(default=None, max_length=64)


class SessionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = Field(default=None, max_length=64)
    focus_app_id: str | None = Field(default=None, max_length=120)
    origin: str = Field(default="shell", pattern="^(shell|avatar)$")
    title: str | None = Field(default=None, max_length=80)


class SessionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=80)
    focus_app_id: str | None = Field(default=None, max_length=120)
    archived: bool | None = None


class SessionMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=8000)
    # Block until Alpha has answered (the avatar); otherwise poll the session.
    wait: bool = False
    # The module on screen when the message was typed, a hint for the loop.
    app_id: str | None = Field(default=None, max_length=120)
    attachments: list[AttachmentIn] = Field(default_factory=list, max_length=MAX_ATTACHMENTS)


def _fail(exc: OperationFailed) -> HTTPException:
    return HTTPException(status_code=HTTP_STATUS.get(exc.code, 500), detail=exc.as_error())


def register(
    app: FastAPI,
    projects: ProjectService,
    sessions: SessionService,
    acting: ActService,
    profile: ProfileService | None = None,
) -> None:
    # ----- projects ------------------------------------------------------------------------

    @app.get("/api/projects")
    def list_projects(include_archived: bool = False) -> dict[str, Any]:
        return {"projects": projects.list_projects(include_archived=include_archived)}

    @app.post("/api/projects", response_model=Project, status_code=201)
    def create_project(body: ProjectDraft) -> Project:
        try:
            return projects.create(body.name, goal=body.goal)
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        """The project with its sessions and its own facts (accepted and suggested)."""
        try:
            project = projects.get(project_id)
        except OperationFailed as exc:
            raise _fail(exc) from exc
        found: dict[str, Any] = {
            "project": project,
            "sessions": sessions.list_sessions(project_id=project_id, scope="project"),
        }
        if profile is not None:
            found["facts"] = profile.view(project_scope(project_id))
        return found

    @app.post("/api/projects/{project_id}", response_model=Project)
    def update_project(project_id: str, body: ProjectPatch) -> Project:
        try:
            return projects.update(
                project_id,
                name=body.name,
                goal=body.goal,
                summary=body.summary,
                archived=body.archived,
            )
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.post("/api/apps/{app_id}/project")
    def file_module(app_id: str, body: FileModule) -> dict[str, Any]:
        """Put a module in a project, or (project_id null) take it out of every project."""
        try:
            projects.file_module(app_id, body.project_id)
        except OperationFailed as exc:
            raise _fail(exc) from exc
        return {"app_id": app_id, "project_id": body.project_id}

    # ----- sessions ------------------------------------------------------------------------

    @app.get("/api/sessions")
    def list_sessions(
        scope: str = Query(default="all", pattern="^(all|global|project|module)$"),
        project_id: str | None = Query(default=None, max_length=64),
        focus_app_id: str | None = Query(default=None, max_length=120),
        limit: int = Query(default=30, ge=1, le=100),
        include_archived: bool = False,
    ) -> dict[str, list[SessionSummary]]:
        return {
            "sessions": sessions.list_sessions(
                project_id=project_id,
                focus_app_id=focus_app_id,
                scope=scope,
                limit=limit,
                include_archived=include_archived,
            )
        }

    @app.get("/api/sessions/search")
    def search_sessions(
        q: str = Query(min_length=1, max_length=400),
        scope: str = Query(default="all", pattern="^(all|global|project)$"),
        project_id: str | None = Query(default=None, max_length=64),
        limit: int = Query(default=10, ge=1, le=50),
    ) -> dict[str, Any]:
        """Verbatim turns that mention the words, best first (keyword search, on this Mac)."""
        return {"hits": sessions.search(q, project_id=project_id, scope=scope, limit=limit)}

    @app.post("/api/sessions", response_model=Session, status_code=201)
    def create_session(body: SessionDraft) -> Session:
        try:
            return sessions.create(
                project_id=body.project_id,
                focus_app_id=body.focus_app_id,
                origin=body.origin,
                title=body.title,
            )
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.get("/api/sessions/{session_id}", response_model=Session)
    def get_session(session_id: str) -> Session:
        try:
            return sessions.get(session_id)
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.post("/api/sessions/{session_id}", response_model=Session)
    def update_session(session_id: str, body: SessionPatch) -> Session:
        try:
            return sessions.update(
                session_id, title=body.title, focus_app_id=body.focus_app_id, archived=body.archived
            )
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.post("/api/sessions/{session_id}/messages", response_model=Session)
    def send_message(session_id: str, body: SessionMessage) -> Session:
        """Say something in the session. Alpha works it through in the background (poll the
        session; its state is `thinking`), or, with `wait`, before this returns."""
        try:
            acting.send(
                session_id,
                body.text,
                wait=body.wait,
                context_app_id=body.app_id,
                attachments=body.attachments,
            )
        except OperationFailed as exc:
            raise _fail(exc) from exc
        except RouteUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return sessions.get(session_id)

    @app.post("/api/sessions/{session_id}/compact", response_model=Session)
    def compact_session(session_id: str) -> Session:
        """Fold the older turns into Alpha's notes now (normally happens on its own)."""
        try:
            return sessions.compact(session_id)
        except OperationFailed as exc:
            raise _fail(exc) from exc
