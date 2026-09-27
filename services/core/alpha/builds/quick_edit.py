"""One structured model call that edits a package's files in place: the quick path for a
change the person asked for, and the repair of a build that failed a few checks. The model
returns whole files; the platform keeps the identity lines, validates the package and runs the
checks. Shared by the creation service (quick changes) and the build service (quick repairs)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

QUICK_MAX_BYTES = 160_000
PACKAGE_FILE_KINDS = (".yaml", ".py", ".md")

QUICK_CHANGE_SYSTEM = (
    "You edit an existing Alpha App directly, the way a careful engineer edits a small "
    "codebase: change exactly what the person asked for, keep everything else as it is, and "
    "return every file you changed in full.\n\n"
    "Rules:\n"
    "- Return only files that change, each as its complete new content. Paths are app.yaml, "
    "or under src/ or tests/. Never invent other paths.\n"
    "- In app.yaml the lines app_id, runtime_profile and sdk_version must stay exactly as they "
    "are. Collections keep every existing field with its name and kind (new fields must be "
    "optional). Action ids stay. Everything a block or view refers to must still exist.\n"
    "- The App contract and SDK reference are provided: follow them for screen blocks, views, "
    "actions and handlers. Python uses only the standard library and alpha_sdk.\n"
    "- Adding an OPTIONAL field to an existing table is fine in a quick change (Alpha migrates "
    "saved records; add its column, detail entry and handler code together). If the change "
    "needs a new table, a required field, a new action, a new capability, a new source to "
    "read, or you cannot tell what is meant, do not guess: set needs_full_build to true and "
    "say why in reason. Exception: letting the App read sites through the person's signed-in "
    "browser is a quick change: add browser to capabilities in app.yaml (ctx.web.get then uses "
    "the session for sites the person allows) and, where the code reports a page that could "
    "not be read, mention page.blocked as needing sign-in.\n"
    "- Write a one-sentence summary of what you changed for the person.\n"
    "Output only the structured object."
)


def quick_change_prompt(request: str, files: dict[str, str], references: str, feedback: str) -> str:
    parts = [f"REQUESTED CHANGE:\n{request}"]
    if feedback:
        parts.append(f"PREVIOUS ATTEMPT:\n{feedback}")
    parts.append("CURRENT FILES:")
    for path, content in files.items():
        parts.append(f"----- {path} -----\n{content}")
    if references:
        parts.append(references)
    return "\n\n".join(parts)


def quick_change_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["files", "summary", "needs_full_build", "reason"],
        "properties": {
            "files": {
                "type": "array",
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["path", "content"],
                    "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                },
            },
            "summary": {"type": "string", "maxLength": 400},
            "needs_full_build": {"type": "boolean"},
            "reason": {"type": "string", "maxLength": 400},
        },
    }


def fake_quick_change(request: str, files: dict[str, str]) -> dict[str, Any]:
    """Control responder: rewrites the App's description to carry the request."""
    text = files.get("app.yaml", "")
    lines = [
        (
            f"description: Changed: {request.strip()[:80]}"
            if line.startswith("description:")
            else line
        )
        for line in text.splitlines()
    ]
    return {
        "files": [{"path": "app.yaml", "content": "\n".join(lines) + "\n"}],
        "summary": f"Changed the description to note: {request.strip()[:60]}",
        "needs_full_build": False,
        "reason": "",
    }


def read_package_files(location: Path) -> dict[str, str]:
    """The files a quick change may see and edit: app.yaml and the sources, in a stable order."""
    found: dict[str, str] = {}
    for path in sorted(location.rglob("*")):
        rel = path.relative_to(location)
        if not path.is_file() or path.suffix not in PACKAGE_FILE_KINDS:
            continue
        top = rel.parts[0]
        if rel.as_posix() != "app.yaml" and top not in ("src", "tests"):
            continue
        if "__pycache__" in rel.parts:
            continue
        found[rel.as_posix()] = path.read_text(encoding="utf-8", errors="replace")
    return found


def apply_edits(package: Path, edits: dict[str, str], source: Any) -> str | None:
    """Write the model's files into the package copy. Returns a problem in words, or None."""
    for rel, content in edits.items():
        if rel.startswith(("/", "..")) or ".." in Path(rel).parts:
            return f"{rel} is not a path inside the package"
        if rel != "app.yaml" and Path(rel).parts[0] not in ("src", "tests"):
            return f"{rel} is outside app.yaml, src/ and tests/"
        if Path(rel).suffix not in PACKAGE_FILE_KINDS:
            return f"{rel} is not a file kind a change may write"
        target = package / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel == "app.yaml":
            content = keep_identity(content, source)
        target.write_text(content, encoding="utf-8")
    return None


def keep_identity(app_yaml: str, source: Any) -> str:
    """The three lines the platform owns stay whatever the model wrote."""
    for key, value in (
        ("app_id", source.app_id),
        ("runtime_profile", source.runtime_profile),
        ("sdk_version", source.sdk_version),
    ):
        app_yaml = re.sub(rf"(?m)^{key}:.*$", f"{key}: {value}", app_yaml, count=1)
    return app_yaml


QUICK_REPAIR_SYSTEM = (
    "You repair an Alpha App that failed some of Alpha's checks. REPAIR.md lists exactly which "
    "checks failed and what was observed; the current files follow. Fix the cause with the "
    "smallest correct change and return every file you changed in full.\n\n"
    "Rules:\n"
    "- Return only files that change, each as its complete new content. Paths are app.yaml, or "
    "under src/ or tests/.\n"
    "- In app.yaml the lines app_id, runtime_profile and sdk_version must stay exactly as they "
    "are. Collections keep every existing field with its name and kind.\n"
    "- The App contract and SDK reference are provided; follow them.\n"
    "- If the failure needs more than a focused edit (a missing feature, a redesign), set "
    "needs_full_build to true and say why in reason; a full builder session then takes over.\n"
    "- Write a one-sentence summary of what you fixed.\n"
    "Output only the structured object."
)


def quick_repair_prompt(repair_md: str, files: dict[str, str], references: str) -> str:
    parts = [f"REPAIR.md:\n{repair_md}", "CURRENT FILES:"]
    for path, content in files.items():
        parts.append(f"----- {path} -----\n{content}")
    if references:
        parts.append(references)
    return "\n\n".join(parts)
