"""The context pack: what Alpha knows, assembled for one request.

Every assistant and avatar turn gets the same pack: the person's profile facts, the modules
they have (with counts), the records that look relevant to what they said, and what happened
recently. Each line says where it came from. The pack is text for a prompt, built fresh each
time; it is not a second data model.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from alpha_contracts.records import AnyOf, Clause, FieldKind, Filter, FilterOp, RecordQuery, SortKey
from alpha_contracts.runs import RunState

from alpha.capabilities.errors import OperationFailed
from alpha.context.profile import ProfileService

log = logging.getLogger("alpha.context")

STOP = frozenset(
    "the a an and or of to in on for with my me our your this that these those from at by as is "
    "are was were be been it its into about over under what which who how when where why do "
    "does did have has had can could would should will shall may might please show tell give "
    "find add log make new some any all more most last next today tomorrow yesterday week "
    "month year days help want need like just also than then them they their you".split()
)
MAX_WORDS = 6
MAX_RECORDS_PER_COLLECTION = 4
MAX_COLLECTIONS = 12
VALUE_CHARS = 60


def keywords(text: str) -> list[str]:
    seen: list[str] = []
    for word in re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", text.lower()):
        if word in STOP or word in seen:
            continue
        seen.append(word)
        if len(seen) >= MAX_WORDS:
            break
    return seen


class ContextPacker:
    def __init__(
        self,
        profile: ProfileService,
        registry: Any,
        records: Any,
        store: Any,
        *,
        names: Any | None = None,
        projects: Any | None = None,
    ) -> None:
        self._profile = profile
        self._registry = registry
        self._records = records
        self._store = store
        self._projects = projects

    def build(self, text: str, *, app_id: str | None = None, project_id: str | None = None) -> str:
        """The pack for one sentence. Cheap enough for every turn: a handful of indexed reads.
        With a project, its own facts and modules come first."""
        sections: list[str] = []
        profile = self._profile.as_text()
        sections.append(
            "ABOUT THE PERSON (accepted profile facts, with their source):\n"
            + (profile or "- nothing recorded yet")
        )
        mine: set[str] = set()
        if project_id and self._projects is not None:
            try:
                mine = set(self._projects.modules_in(project_id))
            except Exception:
                mine = set()
            project_facts = self._profile.as_text(f"project:{project_id}")
            if project_facts:
                sections.append("ABOUT THIS PROJECT (accepted facts):\n" + project_facts)
        sources = self._sources()
        if mine:
            sources.sort(key=lambda item: item[0] not in mine)
        if sources:
            lines = []
            for app, source in sources:
                counts = self._counts(app)
                kept = ", ".join(f"{c.name} ({counts.get(c.name, 0)})" for c in source.collections)
                lines.append(
                    f"- {source.name} [{app}]{' (in this project)' if app in mine else ''}: "
                    f"{source.description}" + (f" Keeps: {kept}." if kept else "")
                )
            sections.append("THEIR MODULES:\n" + "\n".join(lines))
        relevant = self._relevant(text, sources, app_id)
        if relevant:
            sections.append(
                "RECORDS THAT LOOK RELEVANT (from their modules; say which module):\n" + relevant
            )
        recent = self._recent({app: source.name for app, source in sources})
        if recent:
            sections.append("RECENT ACTIVITY:\n" + recent)
        return "\n\n".join(sections)

    # ----- pieces ------------------------------------------------------------------------

    def _sources(self) -> list[tuple[str, Any]]:
        found: list[tuple[str, Any]] = []
        try:
            entries = self._registry.list_apps()
        except Exception:
            return found
        for entry in entries:
            if entry.get("state") != "active":
                continue
            try:
                found.append((entry["app_id"], self._registry.current(entry["app_id"]).source))
            except OperationFailed:
                continue
        return found

    def _counts(self, app_id: str) -> dict[str, int]:
        try:
            counts: dict[str, int] = self._records.store(app_id).counts()
            return counts
        except Exception:
            return {}

    def _relevant(self, text: str, sources: list[tuple[str, Any]], focus: str | None) -> str:
        words = keywords(text)
        if not words:
            return ""
        lines: list[str] = []
        searched = 0
        ordered = sorted(sources, key=lambda s: 0 if s[0] == focus else 1)
        for app_id, source in ordered:
            for collection in source.collections:
                if searched >= MAX_COLLECTIONS:
                    break
                text_fields = [
                    f.name
                    for f in collection.fields
                    if f.kind
                    in (FieldKind.TEXT, FieldKind.LONG_TEXT, FieldKind.CHOICE, FieldKind.STATUS)
                ]
                if not text_fields:
                    continue
                searched += 1
                clauses: list[Filter] = [
                    Clause(field=f, op=FilterOp.CONTAINS, value=w)
                    for f in text_fields
                    for w in words
                ]
                try:
                    page = self._records.store(app_id).query(
                        RecordQuery(
                            collection=collection.name,
                            where=AnyOf(any=clauses),
                            order_by=[SortKey(field="updated_at", direction="desc")],
                            limit=MAX_RECORDS_PER_COLLECTION,
                        )
                    )
                except Exception:
                    log.debug(
                        "relevance search failed for %s.%s", app_id, collection.name, exc_info=True
                    )
                    continue
                for record in page.records:
                    lines.append(
                        f"- {source.name} / {collection.name}: {self._summary(record.values)}"
                    )
        return "\n".join(lines[:24])

    def _summary(self, values: dict[str, Any]) -> str:
        parts = []
        for key, value in values.items():
            if value in (None, "", []):
                continue
            shown = value if isinstance(value, str) else str(value)
            if len(shown) > VALUE_CHARS:
                shown = shown[:VALUE_CHARS] + "…"
            parts.append(f"{key} {shown}")
            if len(parts) >= 6:
                break
        return "; ".join(parts)

    def _recent(self, names: dict[str, str]) -> str:
        """What ran lately in the modules the person has now (never in one that is gone)."""
        try:
            runs = self._store.list_runs(30)
        except Exception:
            return ""
        lines = []
        for run in runs:
            owner = run.owner.model_dump() if hasattr(run.owner, "model_dump") else {}
            if owner.get("app_id") not in names:
                continue
            when = (
                run.created_at.strftime("%d %b %H:%M")
                if hasattr(run.created_at, "strftime")
                else str(run.created_at)[:16]
            )
            state = "ran" if run.state is RunState.SUCCEEDED else run.state.value
            where = names[owner["app_id"]]
            lines.append(f"- {when}: {owner.get('action_id')} in {where} ({state})")
        return "\n".join(lines[:6])
