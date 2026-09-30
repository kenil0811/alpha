"""Removing a module is a clean deletion: the module, its records, its versions, every run and
build, the conversations that made or changed it, the sessions and turns about it, its
schedules, connections, browser access and visits, its fixes and the nudges about it all go,
in the database and on disk. Nothing about it is left for the assistant to "remember".

What stays: accepted facts about the person (they are the person's, wherever they were typed),
what the model service was used for in totals, and sessions about other things (only the turns
about this module leave them).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import stat
import threading
import time
from pathlib import Path
from typing import Any

from alpha.capabilities.errors import OperationFailed, not_found
from alpha.solutions.registry import ANY_RELEASE, AnyRelease
from alpha.storage.control_store import ControlStore

log = logging.getLogger("alpha.purge")

STOP_WAIT_SECONDS = 8.0


class ModulePurge:
    def __init__(
        self,
        store: ControlStore,
        *,
        registry: Any,
        records: Any,
        coordinator: Any,
        creations: Any | None,
        data_dir: Path,
        versions_root: Path,
        builds_root: Path,
        apps_root: Path,
        artifacts_root: Path | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._records = records
        self._coordinator = coordinator
        self._creations = creations
        self._data_dir = data_dir.resolve()
        self._versions_root = versions_root
        self._builds_root = builds_root
        self._apps_root = apps_root
        self._artifacts_root = artifacts_root
        self._lock = threading.Lock()

    # ----- public ------------------------------------------------------------------------

    def leftovers(self) -> list[dict[str, Any]]:
        """Modules taken out of use before removal deleted things: still on this Mac."""
        rows = self._store.query(
            "SELECT app_id, name, updated_at FROM apps WHERE state = 'removed' ORDER BY updated_at"
        )
        return [dict(r) for r in rows]

    def purge_leftovers(self) -> list[dict[str, Any]]:
        return [self.purge(entry["app_id"]) for entry in self.leftovers()]

    def purge(
        self, app_id: str, expected_release_id: str | None | AnyRelease = ANY_RELEASE
    ) -> dict[str, Any]:
        """Delete the module and everything that exists because of it. Returns what went."""
        with self._lock:
            rows = self._store.query("SELECT * FROM apps WHERE app_id = ?", (app_id,))
            if not rows:
                raise not_found("no such module", app_id=app_id)
            name = str(rows[0]["name"])
            if rows[0]["state"] == "active":
                # The release guard decides first; from here the runtime stops offering it.
                self._registry.retire(app_id, expected_release_id)
            self._stop(app_id)
            found = self._collect(app_id, name)
            counts = self._delete_rows(app_id, name, found)
            counts["files"] = self._delete_files(app_id, found)
        log.info("removed %s (%s): %s", name, app_id, counts)
        return {"app_id": app_id, "name": name, "state": "removed", "deleted": counts}

    # ----- stopping ------------------------------------------------------------------------

    def _stop(self, app_id: str) -> None:
        """Nothing of the module may still be running or being made when its rows go."""
        if self._creations is not None:
            for row in self._store.query(
                "SELECT creation_id FROM creations WHERE (app_id = ? OR change_of = ?)"
                " AND state NOT IN ('active', 'failed', 'cancelled')",
                (app_id, app_id),
            ):
                try:
                    self._creations.cancel(row["creation_id"])
                except OperationFailed:
                    pass
                except Exception:
                    log.debug("could not stop %s", row["creation_id"], exc_info=True)
        mine = [r for r in self._coordinator.runs_in_flight() if _owner_app(r) == app_id]
        for run in mine:
            try:
                self._coordinator.cancel(run.run_id)
            except Exception:
                log.debug("could not cancel %s", run.run_id, exc_info=True)
        deadline = time.monotonic() + STOP_WAIT_SECONDS
        while mine and time.monotonic() < deadline:
            mine = [r for r in self._coordinator.runs_in_flight() if _owner_app(r) == app_id]
            if mine:
                time.sleep(0.2)

    # ----- what belongs to it --------------------------------------------------------------

    def _collect(self, app_id: str, name: str) -> dict[str, Any]:
        q = self._store.query
        runs = [
            r["run_id"]
            for r in q(
                "SELECT run_id FROM runs WHERE json_extract(owner_json, '$.app_id') = ?", (app_id,)
            )
        ]
        creations = q(
            "SELECT creation_id, conversation_id, build_id FROM creations"
            " WHERE app_id = ? OR change_of = ?",
            (app_id, app_id),
        )
        conversations = {
            str(r["conversation_id"])
            for r in creations
            if r["conversation_id"] and not str(r["conversation_id"]).startswith("repair:")
        }
        conversations |= {
            r["conversation_id"]
            for r in q("SELECT conversation_id FROM conversations WHERE change_of = ?", (app_id,))
        }
        builds = {str(r["build_id"]) for r in creations if r["build_id"]}
        if self._has("builds"):
            builds |= {
                r["build_id"] for r in q("SELECT build_id FROM builds WHERE app_id = ?", (app_id,))
            }
        versions = q(
            "SELECT version_id, location_ref FROM app_versions WHERE app_id = ?", (app_id,)
        )
        artifacts = (
            q(
                "SELECT artifact_id, sha256 FROM artifacts"
                " WHERE owner_kind = 'app' AND owner_id = ?",
                (app_id,),
            )
            if self._has("artifacts")
            else []
        )
        return {
            "runs": runs,
            "creations": [r["creation_id"] for r in creations],
            "conversations": sorted(conversations),
            "builds": sorted(builds),
            "versions": [(r["version_id"], r["location_ref"]) for r in versions],
            "artifacts": [(r["artifact_id"], r["sha256"]) for r in artifacts],
            "names": [app_id, name],
        }

    # ----- the database --------------------------------------------------------------------

    def _delete_rows(self, app_id: str, name: str, found: dict[str, Any]) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self._store.transaction() as conn:

            def drop(table: str, where: str, params: tuple[Any, ...] = ()) -> None:
                if not self._has(table):
                    return
                cursor = conn.execute(f"DELETE FROM {table} WHERE {where}", params)
                if cursor.rowcount:
                    counts[table] = counts.get(table, 0) + cursor.rowcount

            def drop_in(table: str, column: str, values: list[str]) -> None:
                for start in range(0, len(values), 400):
                    chunk = values[start : start + 400]
                    marks = ",".join("?" for _ in chunk)
                    drop(table, f"{column} IN ({marks})", tuple(chunk))

            self._delete_session_turns(conn, app_id, found["conversations"], counts)
            for table in ("run_events", "broker_tokens", "model_calls", "worker_leases", "runs"):
                drop_in(table, "run_id", found["runs"])
            for table in ("browser_visits", "browser_grants", "app_schedules", "repairs"):
                drop(table, "app_id = ?", (app_id,))
            drop("project_modules", "app_id = ?", (app_id,))
            drop("module_connections", "app_id = ? OR source_app_id = ?", (app_id, app_id))
            for table in ("build_events", "build_attempts", "dependency_requests", "builds"):
                drop_in(table, "build_id", found["builds"])
            drop_in("creations", "creation_id", found["creations"])
            for table in ("briefs", "conversation_turns", "conversations"):
                drop_in(table, "conversation_id", found["conversations"])
            drop("nudges", "module = ? OR module = ?", (app_id, name))
            if self._has("profile_facts"):
                # Facts are never deleted; what this module only suggested is turned down.
                conn.execute(
                    "UPDATE profile_facts SET state = 'rejected' WHERE state = 'suggested'"
                    " AND provenance = 'module' AND source = ?",
                    (app_id,),
                )
            drop_in("artifacts", "artifact_id", [a[0] for a in found["artifacts"]])
            drop("app_releases", "app_id = ?", (app_id,))
            drop("app_versions", "app_id = ?", (app_id,))
            drop("apps", "app_id = ?", (app_id,))
        return counts

    def _delete_session_turns(
        self, conn: Any, app_id: str, conversations: list[str], counts: dict[str, int]
    ) -> None:
        """Sessions about this module go whole; from other sessions, the turns about it (what
        Alpha did with it, and the message that asked) go, and the notes are dropped so nothing
        of it is carried forward."""
        if not self._has("sessions"):
            return
        own = [
            r["session_id"]
            for r in conn.execute(
                "SELECT session_id FROM sessions WHERE project_id IS NULL AND focus_app_id = ?",
                (app_id,),
            ).fetchall()
        ]
        touched: set[str] = set()
        rows = conn.execute(
            "SELECT turn_id, session_id, sequence, detail_json FROM session_turns"
            " WHERE role = 'alpha'"
        ).fetchall()
        doomed: list[str] = []
        for row in rows:
            if row["session_id"] in own:
                continue
            try:
                detail = json.loads(row["detail_json"] or "{}")
            except ValueError:
                detail = {}
            about = detail.get("app_id") == app_id or detail.get("conversation_id") in conversations
            if not about and isinstance(detail.get("open"), dict):
                about = detail["open"].get("app_id") == app_id
            if not about:
                continue
            doomed.append(row["turn_id"])
            touched.add(row["session_id"])
            asked = conn.execute(
                "SELECT turn_id, role FROM session_turns WHERE session_id = ? AND sequence < ?"
                " ORDER BY sequence DESC LIMIT 1",
                (row["session_id"], row["sequence"]),
            ).fetchone()
            if asked is not None and asked["role"] == "user":
                doomed.append(asked["turn_id"])
        for turn_id in doomed:
            conn.execute("DELETE FROM session_turns WHERE turn_id = ?", (turn_id,))
        for session_id in own:
            conn.execute("DELETE FROM session_turns WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        for session_id in touched:
            left = conn.execute(
                "SELECT text FROM session_turns WHERE session_id = ? AND role = 'user'"
                " ORDER BY sequence LIMIT 1",
                (session_id,),
            ).fetchone()
            remaining = conn.execute(
                "SELECT COUNT(*) AS n FROM session_turns WHERE session_id = ?", (session_id,)
            ).fetchone()["n"]
            if not remaining:
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                own.append(session_id)
                continue
            title = " ".join(str(left["text"]).split())[:80] if left else None
            conn.execute(
                "UPDATE sessions SET summary = NULL, summarised_before = 0, title = ?"
                " WHERE session_id = ?",
                (title, session_id),
            )
        conn.execute("UPDATE sessions SET focus_app_id = NULL WHERE focus_app_id = ?", (app_id,))
        if doomed:
            counts["session_turns"] = len(doomed)
        if own:
            counts["sessions"] = len(own)

    # ----- the disk ------------------------------------------------------------------------

    def _delete_files(self, app_id: str, found: dict[str, Any]) -> int:
        removed = 0
        try:
            self._records.drop(app_id)
        except Exception:
            log.debug("could not close the record store of %s", app_id, exc_info=True)
        removed += self._rmtree(self._apps_root / app_id)
        for _version_id, location in found["versions"]:
            removed += self._rmtree(Path(location))
        for build_id in found["builds"]:
            removed += self._rmtree(self._builds_root / build_id)
        if self._artifacts_root is not None and self._has("artifacts"):
            for _artifact_id, digest in found["artifacts"]:
                still = self._store.query(
                    "SELECT 1 FROM artifacts WHERE sha256 = ? LIMIT 1", (digest,)
                )
                if still or not digest:
                    continue
                blob = self._artifacts_root / "blobs" / "sha256" / str(digest)[:2] / str(digest)
                if self._inside(blob) and blob.is_file():
                    blob.unlink(missing_ok=True)
                    removed += 1
        return removed

    def _rmtree(self, path: Path) -> int:
        """Delete a directory that lies inside Alpha's own data directory, and only then."""
        if not self._inside(path) or not path.exists():
            return 0

        def writable(function: Any, target: str, _error: Any) -> None:
            # Sealed versions are read-only; make the entry and its parent writable and retry.
            try:
                os.chmod(os.path.dirname(target), stat.S_IRWXU)
                os.chmod(target, stat.S_IRWXU)
                function(target)
            except OSError:
                log.debug("could not delete %s", target, exc_info=True)

        shutil.rmtree(path, onerror=writable)
        return 0 if path.exists() else 1

    def _inside(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
        except OSError:
            return False
        return resolved != self._data_dir and self._data_dir in resolved.parents

    def _has(self, table: str) -> bool:
        rows = self._store.query(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?", (table,)
        )
        return bool(rows)


def _owner_app(run: Any) -> str | None:
    owner = getattr(run, "owner", None)
    return getattr(owner, "app_id", None)
