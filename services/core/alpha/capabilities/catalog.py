"""CapabilityCatalog: what Alpha can do right now, with unmet prerequisites stated.

The assistant and builder plan against this list, never against a model's prior knowledge of a
service (Resource Context and Integration Architecture, "Provider order"). A family is available
only when a person can get a working solution that uses it, not when the platform part alone
exists: records, runtime model calls and the interaction kit became available with the creation
and delivery loop (F08); files wait until a person can open or save them (F11). An unavailable
family names the ticket and the reason so the assistant can explain a useful partial outcome
honestly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from alpha.execution.profiles import ProfileInventory


@dataclass(frozen=True)
class CapabilityFamily:
    family: str
    description: str
    available: bool
    operations: tuple[str, ...] = ()
    unavailable_reason: str | None = None
    arrives_with: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


CATALOG: tuple[CapabilityFamily, ...] = (
    CapabilityFamily(
        family="compute",
        description="Pure computation in generated Python actions: parsing, calculation, "
        "transformation of text and numbers supplied as input.",
        available=True,
        operations=("action.invoke",),
        notes=("No files, network, records or credentials inside pure actions.",),
    ),
    CapabilityFamily(
        family="records",
        description="User-owned records with validated fields, history, filtering, totals and "
        "trends, kept on this Mac.",
        available=True,
        operations=(
            "records.create(collection, values)",
            "records.update(collection, id, expected_revision, changes)",
            "records.correct(collection, id, expected_revision, changes)",
            "records.delete(collection, id, expected_revision)",
            "records.get(collection, id)",
            "records.query(collection, where, order_by, limit, cursor)",
            "records.aggregate(collection, metrics, group_by, where)",
            "records.batch(operations)",
        ),
        notes=("Each App has its own records; no App can read another App's records.",),
    ),
    CapabilityFamily(
        family="artifacts",
        description="Files produced by a solution (reports, exports) that the person opens or "
        "saves.",
        # The backend keeps files with their origin (F05), but no Alpha surface lets a person open
        # or save one yet, so a file result would be an unusable handle (M1 review finding F12).
        available=False,
        operations=(
            "artifacts.create(display_name, content, media_type)",
            "artifacts.read(artifact_id)",
            "artifacts.get(artifact_id)",
        ),
        unavailable_reason="Alpha can keep files a solution makes, but you can't open or save them "
        "from Alpha yet",
        arrives_with="F11",
    ),
    CapabilityFamily(
        family="models",
        description="Bounded model calls at runtime for estimates, classification and "
        "extraction, labelled as estimates and correctable.",
        available=True,
        operations=("models.structured(instruction, input, fields)",),
        notes=("At most 10 model calls per action run; results are labelled estimates.",),
    ),
    CapabilityFamily(
        family="custom_ui",
        description="A generated interface for quick entry, lists, review, details and trends, "
        "built from Alpha's interaction kit.",
        available=True,
        operations=("ui.views (declared read views)", "ui.actions (declared UI actions)"),
    ),
    CapabilityFamily(
        family="files",
        description="Reading selected files and folders the user picks explicitly.",
        available=False,
        unavailable_reason="selected-file access is not connected yet",
        arrives_with="F13",
    ),
    CapabilityFamily(
        family="http",
        description="Reading public web pages and JSON APIs, and searching the web, on the "
        "solution's behalf: prices, listings, articles, public data.",
        available=True,
        operations=(
            "http.get(url, max_chars, raw) -> readable text (HTML reduced) or the raw body",
            "http.search(query, count) -> titles, addresses and snippets",
        ),
        notes=(
            "Public http(s) addresses only; nothing on this Mac or a private network.",
            "At most 60 web requests per action run; bodies are capped at 2 MB.",
            "No sign-in: sites that need an account or a browser session are not reachable "
            "this way (that is the browser family).",
        ),
    ),
    CapabilityFamily(
        family="browser",
        description="Working inside websites with a dedicated signed-in browser session, "
        "including filling supported forms.",
        available=False,
        unavailable_reason="browser sessions are not connected yet",
        arrives_with="F14",
    ),
    CapabilityFamily(
        family="messaging",
        description="Sending messages or notifications through chat or email services.",
        available=False,
        unavailable_reason="no messaging service is connected and none is planned for the "
        "first release",
        arrives_with=None,
    ),
    CapabilityFamily(
        family="schedules",
        description="Running one of a solution's actions on a local schedule (every N minutes, "
        "or daily at a time) while Alpha is running, with last and next run shown and an on/off "
        "switch.",
        available=True,
        operations=(
            "schedules (declared in app.yaml: id, title, action, every_minutes | daily_at)",
        ),
        notes=(
            "Runs only while Alpha is open on this Mac; missed times are never caught up.",
            "The scheduled action must list trigger in invocable_from.",
        ),
    ),
    CapabilityFamily(
        family="audio",
        description="Generating or transcribing audio.",
        available=False,
        unavailable_reason="no audio provider is connected",
        arrives_with=None,
    ),
)


def catalog_entries() -> list[dict[str, object]]:
    return [
        {
            "family": c.family,
            "description": c.description,
            "available": c.available,
            "operations": list(c.operations),
            "unavailable_reason": c.unavailable_reason,
            "arrives_with": c.arrives_with,
            "notes": list(c.notes),
        }
        for c in CATALOG
    ]


def profile_versions(inventory: ProfileInventory) -> dict[str, Any]:
    """The runtime and UI build profiles new solutions are built against right now."""
    found: dict[str, Any] = {}
    runtime = inventory.default_app_profile()
    if runtime is not None:
        pins = {p.name: p.version for p in runtime.profile.packages}
        found["runtime"] = {
            "profile_id": runtime.profile_id,
            "python": runtime.profile.target.python_version,
            "sdk": pins.get("alpha-sdk"),
        }
    ui = inventory.default_ui_profile()
    if ui is not None:
        pins = {p.name: p.version for p in ui.profile.packages}
        found["ui_build"] = {
            "profile_id": ui.profile_id,
            "kit": pins.get("@alpha/ui-kit"),
            "bridge": pins.get("@alpha/ui-bridge"),
            "react": pins.get("react"),
        }
    return found


def available_families() -> set[str]:
    return {c.family for c in CATALOG if c.available}


def catalog_prompt_text() -> str:
    """Plain rendering for the assistant's system prompt."""
    lines = ["Capabilities Alpha has RIGHT NOW (plan only with these):"]
    for c in CATALOG:
        if c.available:
            lines.append(f"- {c.family}: AVAILABLE. {c.description}")
    lines.append(
        "Capabilities that are NOT available yet (name them as unavailable; do not promise them):"
    )
    for c in CATALOG:
        if not c.available:
            when = (
                f" (planned: {c.arrives_with})"
                if c.arrives_with
                else " (not planned for the first release)"
            )
            lines.append(
                f"- {c.family}: unavailable, {c.unavailable_reason}{when}. {c.description}"
            )
    return "\n".join(lines)
