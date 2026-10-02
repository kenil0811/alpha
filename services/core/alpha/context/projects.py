"""Projects: a goal in the person's life that groups modules and the sessions about them.

A project is optional (a module that belongs to none is "unfiled") and never a permission
boundary: on one person's Mac, scope decides what the assistant attends to and where a learned
fact is filed, nothing more. A module belongs to at most one project. Alpha's own notes about a
project (`summary`) are written by the session consolidation and are the person's to edit or
clear; the goal is in the person's words.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alpha_contracts.briefs import SolutionBrief
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
UNTITLED = "Untitled project"

# The icons a project may show (lucide names the shell draws).
PROJECT_ICONS = (
    "folder",
    "briefcase",
    "notebook-pen",
    "calendar",
    "users",
    "chart-line",
    "mail",
    "list-checks",
    "graduation-cap",
    "heart-pulse",
    "wallet",
    "shopping-cart",
    "plane",
    "house",
    "code",
    "megaphone",
    "book-open",
    "sparkles",
    "sticky-note",
    "target",
)
# The files Alpha keeps for a project: its plan and the bugs found while making it.
PROJECT_FILES = ("plan.md", "bugs.md")


def _now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


class Project(BaseModel):
    project_id: str
    name: str
    goal: str | None = None
    # Alpha's notes on the project, kept up to date from its sessions; editable by the person.
    summary: str | None = None
    icon: str | None = None
    modules: list[str]
    created_at: str
    updated_at: str
    archived_at: str | None = None


class ProjectService:
    def __init__(self, store: ControlStore, files_root: Path | None = None) -> None:
        self._store = store
        # Where each project's files live (one folder per project); None keeps no files.
        self._files_root = files_root
        self._lock = threading.Lock()
        store.execute_script(_SCHEMA)
        store.add_missing_columns("projects", {"icon": "TEXT"})

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
        icon: str | None = None,
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
        if icon is not None:
            if icon not in PROJECT_ICONS:
                raise invalid("unknown project icon", icon=icon)
            sets.append("icon = ?")
            values.append(icon)
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

    # ----- files -------------------------------------------------------------------------

    def read_file(self, project_id: str, name: str) -> dict[str, Any] | None:
        """One of the project's files ({name, text, updated_at}), or None when it is absent."""
        path = self._file_path(project_id, name)
        if path is None or not path.is_file():
            return None
        updated = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        return {
            "name": name,
            "text": path.read_text(encoding="utf-8"),
            "updated_at": updated.isoformat().replace("+00:00", "Z"),
        }

    def write_file(self, project_id: str, name: str, text: str) -> None:
        path = self._file_path(project_id, name)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)

    def _file_path(self, project_id: str, name: str) -> Path | None:
        if name not in PROJECT_FILES:
            raise invalid("unknown project file", name=name)
        self.get(project_id)  # an unknown project is not_found; its id is then a safe folder name
        return self._files_root / project_id / name if self._files_root else None

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
            icon=row["icon"] if "icon" in row.keys() else None,
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


# The shell's words for a capability family (apps/desktop/src/assistant/plain.ts).
_CAPABILITY_LABELS = {
    "compute": "calculations on what you type",
    "records": "keeping your entries and history",
    "artifacts": "producing files",
    "models": "estimates and classification",
    "custom_ui": "its own screen",
    "files": "reading your files",
    "http": "reading websites and services",
    "browser": "working inside websites",
    "profile": "what Alpha knows about you",
    "messaging": "sending messages",
    "schedules": "running on a schedule",
    "audio": "audio",
}
_FIELD_KINDS = {
    "number": "a number",
    "boolean": "yes/no",
    "date": "a date",
    "datetime": "a date and time",
    "choice": "one of a few choices",
    "reference": "a link to another entry",
    "json": "structured details",
}
_SOURCES = {
    "model_default": "default",
    "user_answer": "you chose",
    "user_correction": "you corrected",
}


def brief_markdown(brief: SolutionBrief, data_notice: str | None = None) -> str:
    """The project's plan.md: the brief, as the person reads it on the brief card."""
    out = [f"# {brief.goal}", "", brief.success_summary, ""]
    if brief.primary_journey:
        out.append("## How you'll use it")
        out += [
            f"{i}. {s.action}: {s.expected_result}" for i, s in enumerate(brief.primary_journey, 1)
        ]
        out.append("")
    if brief.data_needs:
        out.append("## What it keeps")
        for need in brief.data_needs:
            fields = ", ".join(
                f"{f.name.replace('_', ' ')} ({_FIELD_KINDS.get(f.kind, f.kind)})"
                for f in need.fields
            )
            out.append(f"- {need.collection.replace('_', ' ')}: {fields}")
        out.append("")
    if brief.assumptions:
        out.append("## Assumptions you can change")
        out += [f"- {a.text} ({_SOURCES.get(a.source, a.source)})" for a in brief.assumptions]
        out.append("")
    if brief.unavailable_capabilities:
        out.append("## Not possible yet")
        out += [
            f"- {_CAPABILITY_LABELS.get(c, c.replace('_', ' '))}"
            for c in brief.unavailable_capabilities
        ]
        out.append("")
    if data_notice:
        out += ["## Where your data goes", data_notice, ""]
    return "\n".join(out)
