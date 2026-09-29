"""Projects: a goal in the person's life that groups modules and the sessions about them.

A project is optional (a module that belongs to none is "unfiled") and never a permission
boundary: on one person's Mac, scope decides what the assistant attends to and where a learned
fact is filed, nothing more. A module belongs to at most one project. Alpha's own notes about a
project (`summary`) are written by the session consolidation and are the person's to edit or
clear; the goal is in the person's words.
"""

from __future__ import annotations

import threading
from typing import Any

from pydantic import BaseModel

from alpha.capabilities.errors import invalid, not_found
from alpha.storage.control_store import ControlStore, new_id, utc_now

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    goal TEXT,
    summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);
CREATE TABLE IF NOT EXISTS project_modules (
    app_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    filed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS project_modules_project ON project_modules(project_id);
"""

MAX_NAME = 80
MAX_GOAL = 600
MAX_SUMMARY = 4000


def _now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


class Project(BaseModel):
    project_id: str
    name: str
    goal: str | None = None
    # Alpha's notes on the project, kept up to date from its sessions; editable by the person.
    summary: str | None = None
    modules: list[str]
    created_at: str
    updated_at: str
    archived_at: str | None = None


class ProjectService:
    def __init__(self, store: ControlStore) -> None:
        self._store = store
        self._lock = threading.Lock()
        store.execute_script(_SCHEMA)

    # ----- reading -----------------------------------------------------------------------

    def list_projects(self, *, include_archived: bool = False) -> list[Project]:
        rows = self._store.query(
            "SELECT * FROM projects"
            + ("" if include_archived else " WHERE archived_at IS NULL")
            + " ORDER BY created_at"
        )
        modules = self._modules_by_project()
        return [self._project(r, modules.get(r["project_id"], [])) for r in rows]

    def get(self, project_id: str) -> Project:
        rows = self._store.query("SELECT * FROM projects WHERE project_id = ?", (project_id,))
        if not rows:
            raise not_found("no such project", project_id=project_id)
        return self._project(rows[0], self.modules_in(project_id))

    def modules_in(self, project_id: str) -> list[str]:
        rows = self._store.query(
            "SELECT app_id FROM project_modules WHERE project_id = ? ORDER BY filed_at",
            (project_id,),
        )
        return [r["app_id"] for r in rows]

    def project_of(self, app_id: str) -> str | None:
        rows = self._store.query(
            "SELECT project_id FROM project_modules WHERE app_id = ?", (app_id,)
        )
        return rows[0]["project_id"] if rows else None

    def names(self) -> dict[str, str]:
        return {p.project_id: p.name for p in self.list_projects(include_archived=True)}

    # ----- writing -----------------------------------------------------------------------

    def create(self, name: str, *, goal: str | None = None) -> Project:
        clean = " ".join(name.split())
        if not clean:
            raise invalid("a project needs a name")
        now = _now()
        project_id = new_id("proj")
        with self._lock, self._store.transaction() as conn:
            conn.execute(
                "INSERT INTO projects(project_id, name, goal, created_at, updated_at)"
                " VALUES (?,?,?,?,?)",
                (project_id, clean[:MAX_NAME], _clip(goal, MAX_GOAL), now, now),
            )
        return self.get(project_id)

    def update(
        self,
        project_id: str,
        *,
        name: str | None = None,
        goal: str | None = None,
        summary: str | None = None,
        archived: bool | None = None,
    ) -> Project:
        self.get(project_id)
        sets: list[str] = []
        values: list[Any] = []
        if name is not None:
            clean = " ".join(name.split())
            if not clean:
                raise invalid("a project needs a name")
            sets.append("name = ?")
            values.append(clean[:MAX_NAME])
        if goal is not None:
            sets.append("goal = ?")
            values.append(_clip(goal, MAX_GOAL))
        if summary is not None:
            sets.append("summary = ?")
            values.append(_clip(summary, MAX_SUMMARY))
        if archived is not None:
            sets.append("archived_at = ?")
            values.append(_now() if archived else None)
        if not sets:
            return self.get(project_id)
        sets.append("updated_at = ?")
        values.append(_now())
        values.append(project_id)
        with self._lock, self._store.transaction() as conn:
            conn.execute(f"UPDATE projects SET {', '.join(sets)} WHERE project_id = ?", values)
        return self.get(project_id)

    def file_module(self, app_id: str, project_id: str | None) -> None:
        """Put a module in a project (moving it out of any other), or (None) unfile it."""
        if project_id is not None:
            self.get(project_id)
        with self._lock, self._store.transaction() as conn:
            conn.execute("DELETE FROM project_modules WHERE app_id = ?", (app_id,))
            if project_id is not None:
                conn.execute(
                    "INSERT INTO project_modules(app_id, project_id, filed_at) VALUES (?,?,?)",
                    (app_id, project_id, _now()),
                )

    # ----- pieces ------------------------------------------------------------------------

    def _modules_by_project(self) -> dict[str, list[str]]:
        found: dict[str, list[str]] = {}
        rows = self._store.query("SELECT app_id, project_id FROM project_modules ORDER BY filed_at")
        for row in rows:
            found.setdefault(row["project_id"], []).append(row["app_id"])
        return found

    @staticmethod
    def _project(row: Any, modules: list[str]) -> Project:
        return Project(
            project_id=row["project_id"],
            name=row["name"],
            goal=row["goal"],
            summary=row["summary"],
            modules=modules,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            archived_at=row["archived_at"],
        )


def _clip(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    clean = text.strip()
    return clean[:limit] if clean else None
