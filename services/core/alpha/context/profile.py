"""The profile store: append-only facts about the person with provenance and supersession.

The living profile is a read over accepted facts: for each field, the newest accepted claim.
A module writes what the person typed into it as an accepted fact (provenance `module`); what
a module or the assistant infers is a suggestion until the person accepts it. Corrections and
forgetting never delete rows: a correction supersedes, forgetting retracts.
"""

from __future__ import annotations

import json
import threading
from typing import Any

from alpha_contracts.profile import FactProvenance, ProfileFact, ProfileView

from alpha.capabilities.errors import invalid, not_found
from alpha.storage.control_store import ControlStore, new_id, utc_now

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profile_facts (
    fact_id TEXT PRIMARY KEY,
    field TEXT NOT NULL,
    value_json TEXT NOT NULL,
    provenance TEXT NOT NULL,
    source TEXT NOT NULL,
    why TEXT,
    confidence REAL NOT NULL,
    state TEXT NOT NULL,
    supersedes TEXT,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS profile_facts_field ON profile_facts(field, recorded_at);
"""

MAX_FACTS_PER_FIELD_HISTORY = 50


def _now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


class ProfileService:
    def __init__(self, store: ControlStore) -> None:
        self._store = store
        self._lock = threading.Lock()
        store.execute_script(_SCHEMA)

    # ----- reading -----------------------------------------------------------------------

    def view(self) -> ProfileView:
        return ProfileView(facts=self.current(), suggestions=self.suggestions())

    def current(self) -> list[ProfileFact]:
        """The newest accepted fact per field, oldest field first."""
        rows = self._store.query(
            "SELECT * FROM profile_facts WHERE state = 'accepted' ORDER BY recorded_at"
        )
        latest: dict[str, ProfileFact] = {}
        for row in rows:
            fact = self._fact(row)
            latest[fact.field] = fact
        return list(latest.values())

    def get(self, field: str) -> ProfileFact | None:
        return next((f for f in self.current() if f.field == field), None)

    def suggestions(self) -> list[ProfileFact]:
        rows = self._store.query(
            "SELECT * FROM profile_facts WHERE state = 'suggested' ORDER BY recorded_at"
        )
        return [self._fact(r) for r in rows]

    def history(self, field: str) -> list[ProfileFact]:
        rows = self._store.query(
            "SELECT * FROM profile_facts WHERE field = ? ORDER BY recorded_at DESC LIMIT ?",
            (field, MAX_FACTS_PER_FIELD_HISTORY),
        )
        return [self._fact(r) for r in rows]

    def as_text(self) -> str:
        """The living profile in plain lines for a prompt, with where each fact came from."""
        facts = self.current()
        if not facts:
            return ""
        lines = []
        for fact in facts:
            value = fact.value if isinstance(fact.value, str) else json.dumps(fact.value)
            source = {
                "person": "they said so",
                "module": f"from {fact.source}",
                "assistant": "from a conversation",
                "inferred": "inferred, accepted",
            }[fact.provenance]
            lines.append(f"- {fact.field.replace('_', ' ')}: {value} ({source})")
        return "\n".join(lines)

    # ----- writing -----------------------------------------------------------------------

    def claim(
        self,
        field: str,
        value: Any,
        *,
        provenance: FactProvenance,
        source: str,
        why: str | None = None,
        confidence: float = 1.0,
        accepted: bool,
    ) -> ProfileFact:
        """Record a claim. Accepted claims supersede the field's current accepted fact; a
        suggestion waits. A claim identical to the current fact records nothing new."""
        if value is None or value == "" or value == []:
            raise invalid("a fact needs a value", field=field)
        encoded = json.dumps(value, sort_keys=True, default=str)
        if len(encoded) > 4000:
            raise invalid("a fact is at most 4000 characters", field=field)
        with self._lock, self._store.transaction() as conn:
            current = conn.execute(
                "SELECT * FROM profile_facts WHERE field = ? AND state = 'accepted'"
                " ORDER BY recorded_at DESC LIMIT 1",
                (field,),
            ).fetchone()
            if current is not None and current["value_json"] == encoded and accepted:
                return self._fact(current)
            if not accepted:
                pending = conn.execute(
                    "SELECT * FROM profile_facts WHERE field = ? AND state = 'suggested'"
                    " AND value_json = ? LIMIT 1",
                    (field, encoded),
                ).fetchone()
                if pending is not None:
                    return self._fact(pending)
            fact_id = new_id("fact")
            supersedes = current["fact_id"] if (current is not None and accepted) else None
            conn.execute(
                """INSERT INTO profile_facts(fact_id, field, value_json, provenance, source, why,
                   confidence, state, supersedes, recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    fact_id,
                    field,
                    encoded,
                    provenance,
                    source[:120],
                    why,
                    float(confidence),
                    "accepted" if accepted else "suggested",
                    supersedes,
                    _now(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM profile_facts WHERE fact_id = ?", (fact_id,)
            ).fetchone()
        return self._fact(row)

    def accept(self, fact_id: str) -> ProfileFact:
        """The person agrees with a suggestion: it becomes the field's accepted fact."""
        with self._lock, self._store.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM profile_facts WHERE fact_id = ?", (fact_id,)
            ).fetchone()
            if row is None:
                raise not_found("no such fact", fact_id=fact_id)
            if row["state"] != "suggested":
                return self._fact(row)
            current = conn.execute(
                "SELECT fact_id FROM profile_facts WHERE field = ? AND state = 'accepted'"
                " ORDER BY recorded_at DESC LIMIT 1",
                (row["field"],),
            ).fetchone()
            conn.execute(
                "UPDATE profile_facts SET state = 'accepted', supersedes = ?, recorded_at = ?"
                " WHERE fact_id = ?",
                (current["fact_id"] if current else None, _now(), fact_id),
            )
            row = conn.execute(
                "SELECT * FROM profile_facts WHERE fact_id = ?", (fact_id,)
            ).fetchone()
        return self._fact(row)

    def reject(self, fact_id: str) -> None:
        self._set_state(fact_id, "rejected", only_from="suggested")

    def forget(self, fact_id: str) -> None:
        """The person no longer wants this known: the fact is retracted (kept for the record,
        never shown or used again)."""
        self._set_state(fact_id, "retracted", only_from=None)

    def _set_state(self, fact_id: str, state: str, *, only_from: str | None) -> None:
        with self._lock, self._store.transaction() as conn:
            row = conn.execute(
                "SELECT state FROM profile_facts WHERE fact_id = ?", (fact_id,)
            ).fetchone()
            if row is None:
                raise not_found("no such fact", fact_id=fact_id)
            if only_from is not None and row["state"] != only_from:
                return
            conn.execute("UPDATE profile_facts SET state = ? WHERE fact_id = ?", (state, fact_id))

    def _fact(self, row: Any) -> ProfileFact:
        return ProfileFact(
            fact_id=row["fact_id"],
            field=row["field"],
            value=json.loads(row["value_json"]),
            provenance=row["provenance"],
            source=row["source"],
            why=row["why"],
            confidence=row["confidence"],
            state=row["state"],
            supersedes=row["supersedes"],
            recorded_at=row["recorded_at"],
        )
