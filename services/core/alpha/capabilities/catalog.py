"""CapabilityCatalog: what Alpha can do right now, with unmet prerequisites stated.

The assistant and builder plan against this list, never against a model's prior knowledge of a
service (Resource Context and Integration Architecture, "Provider order"). Entries flip to
available only when the owning ticket lands; an unavailable family names the ticket and the
reason so the assistant can explain a useful partial outcome honestly.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
        available=False,
        unavailable_reason="record storage for generated solutions is not connected yet",
        arrives_with="F05",
    ),
    CapabilityFamily(
        family="artifacts",
        description="Files produced or transformed by a solution (reports, exports).",
        available=False,
        unavailable_reason="file outputs are not connected yet",
        arrives_with="F05",
    ),
    CapabilityFamily(
        family="models",
        description="Bounded model calls at runtime for estimates, classification and "
        "extraction, labelled as estimates and correctable.",
        available=False,
        unavailable_reason="runtime model calls for solutions are not connected yet",
        arrives_with="F05",
    ),
    CapabilityFamily(
        family="custom_ui",
        description="A generated interface for quick entry, lists, details and trends.",
        available=False,
        unavailable_reason="the shared interaction kit is not built yet",
        arrives_with="F06",
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
        description="Reading public web sources and qualified APIs.",
        available=False,
        unavailable_reason="web and API access is not connected yet",
        arrives_with="F13",
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
        description="Running a solution on a local schedule while Alpha is running.",
        available=False,
        unavailable_reason="local schedules are not connected yet",
        arrives_with="F17",
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
