"""Settings the person can change from the shell: which model each stage uses and how much a
build may spend. Kept in the control store, read at the moment they matter (no restart), and
described with plain titles so the Settings page needs no knowledge of its own."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from alpha.solutions.conventions import DEFAULT_CONVENTIONS
from alpha.storage.control_store import ControlStore, utc_now

MODEL_OPTIONS: tuple[tuple[str, str], ...] = (
    ("default", "Claude Code's default"),
    ("opus", "Claude Opus (most capable)"),
    ("sonnet", "Claude Sonnet (faster)"),
    ("haiku", "Claude Haiku (fastest)"),
)

# The provider every stage uses. "claude" (Console-account sign-in) is the default: it needs no
# key and keeps working even where a Claude subscription sign-in is turned off (founder decision
# 2026-09-25). The others are the person's explicit choice, made in Settings -> Models.
PROVIDER_OPTIONS: tuple[tuple[str, str], ...] = (
    ("claude", "Claude (signed in)"),
    ("claude_api", "Claude (API key)"),
    ("chatgpt_codex", "ChatGPT (signed in with Codex)"),
    ("chatgpt_api", "ChatGPT (API key)"),
    ("openrouter", "OpenRouter"),
    ("grok", "Grok"),
)

# The person's default governance stance, shown in Settings and offered as the + menu's starting
# point for every new session (a session that has chosen its own stays on it). "ask" is the
# default: it is the strictest of the three, kept as the safe out-of-box behaviour rather than
# defaulting to "approve_for_me" (AP-182 still requires universal user approval for anything
# unaudited; nothing in Core's execution path asked for approval before this setting existed, so
# "ask" is a new, stricter floor, not a preservation of the old unrestricted behaviour).
ACCESS_MODE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("ask", "Ask for approval"),
    ("approve_for_me", "Approve for me"),
    ("full", "Full access"),
)


@dataclass(frozen=True)
class SettingField:
    id: str
    group: str
    title: str
    description: str
    kind: str  # "choice" | "integer" | "text"
    default: Any
    options: tuple[tuple[str, str], ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    unit: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _model(id: str, title: str, description: str, default: str = "default") -> SettingField:
    return SettingField(id, "Models", title, description, "choice", default, MODEL_OPTIONS)


FIELDS: tuple[SettingField, ...] = (
    _model(
        "models.assistant",
        "Model for the assistant",
        "Understands your request and writes the plan you approve. Sonnet answers in about "
        "half the time of Opus and is enough for this.",
        "sonnet",
    ),
    _model(
        "models.planner",
        "Model for the checks",
        "Writes the checks a project must pass before it is switched on.",
        "sonnet",
    ),
    _model(
        "models.builder_new",
        "Model for building a new project",
        "Writes the project's code and screen. The most capable model gives the best projects.",
    ),
    _model(
        "models.builder_change",
        "Model for changing a project",
        "Edits an existing project when you ask for a change.",
    ),
    _model(
        "models.app",
        "Model projects use while running",
        "Estimates, scoring and summaries a project asks for while you use it. Faster models "
        "make checks and scoring feel quick.",
        "sonnet",
    ),
    SettingField(
        "models.provider",
        "Models",
        "Provider",
        "Which account or key every stage uses. Claude needs no key and is the default; the "
        "others use the account or key you connect below.",
        "choice",
        "claude",
        PROVIDER_OPTIONS,
    ),
    SettingField(
        "models.chatgpt_model",
        "Models",
        "ChatGPT model (API key)",
        "The OpenAI model id to use when ChatGPT is connected with an API key.",
        "text",
        "gpt-4o-mini",
        maximum=100,
    ),
    SettingField(
        "models.openrouter_model",
        "Models",
        "OpenRouter model",
        "The OpenRouter model id to use, for example openai/gpt-4o-mini.",
        "text",
        "openai/gpt-4o-mini",
        maximum=100,
    ),
    SettingField(
        "models.grok_model",
        "Models",
        "Grok model",
        "The xAI model id to use, for example grok-4.",
        "text",
        "grok-4",
        maximum=100,
    ),
    SettingField(
        "build.fast_lane",
        "Building limits",
        "Projects go live early",
        "A project is switched on as soon as its structure checks out (its package, code and "
        "actions are sound); the deeper behaviour checks run while you already use it, and you "
        "can go back with one click if they find a problem. Off waits for every check first.",
        "choice",
        "on",
        (("on", "On"), ("off", "Off: check everything first")),
    ),
    SettingField(
        "build.max_turns",
        "Building limits",
        "Steps per build attempt",
        "How many steps the builder may take before an attempt is stopped.",
        "integer",
        90,
        minimum=20,
        maximum=200,
    ),
    SettingField(
        "build.max_attempt_minutes",
        "Building limits",
        "Minutes per attempt",
        "An attempt that runs longer is stopped and repaired or given up.",
        "integer",
        15,
        minimum=3,
        maximum=40,
        unit="min",
    ),
    SettingField(
        "build.max_total_minutes",
        "Building limits",
        "Minutes for the whole build",
        "Across every attempt, including repairs.",
        "integer",
        40,
        minimum=5,
        maximum=120,
        unit="min",
    ),
    SettingField(
        "build.max_repair_attempts",
        "Building limits",
        "Repair attempts",
        "How many times a project that failed its checks is repaired before giving up.",
        "integer",
        2,
        minimum=0,
        maximum=4,
    ),
)
FIELDS = (
    *FIELDS,
    SettingField(
        "browser.pages_per_hour",
        "Signed-in browser",
        "Pages per hour, per site",
        "How many pages a project may open through your signed-in browser in an hour. Low "
        "numbers look like a person and keep accounts safe.",
        "integer",
        30,
        minimum=5,
        maximum=200,
    ),
    SettingField(
        "browser.min_seconds_between_pages",
        "Signed-in browser",
        "Seconds between pages",
        "The shortest gap between two pages opened on the same site.",
        "integer",
        15,
        minimum=3,
        maximum=120,
        unit="s",
    ),
    SettingField(
        "access.mode",
        "Access",
        "When Alpha needs your OK",
        "Ask for approval: always ask before editing files outside a project or using the "
        "internet. Approve for me: only ask for actions detected as unsafe (deletes, sends, "
        "payments). Full access: no approval prompts (a secret leak or a permanent delete of "
        "your data still confirms).",
        "choice",
        "ask",
        ACCESS_MODE_OPTIONS,
    ),
    SettingField(
        "look.density",
        "Look",
        "Density",
        "How much room forms, tables and cards take. Compact fits more on screen.",
        "choice",
        "compact",
        (("compact", "Compact"), ("comfortable", "Comfortable")),
    ),
    SettingField(
        "look.rules",
        "Look",
        "Rules for how projects should look and behave",
        "Alpha's defaults, in plain sentences, followed when it builds or changes any project. "
        "Edit them to your taste or reset to Alpha's.",
        "text",
        DEFAULT_CONVENTIONS,
        maximum=3000,
    ),
)
BY_ID = {f.id: f for f in FIELDS}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class InvalidSetting(ValueError):
    pass


class Preferences:
    def __init__(self, store: ControlStore) -> None:
        self._store = store
        store.execute_script(_SCHEMA)

    def get(self, field_id: str) -> Any:
        spec = BY_ID[field_id]
        rows = self._store.query("SELECT value_json FROM preferences WHERE key = ?", (field_id,))
        if not rows:
            return spec.default
        value = json.loads(rows[0]["value_json"])
        return value if self._valid(spec, value) is None else spec.default

    def values(self) -> dict[str, Any]:
        return {f.id: self.get(f.id) for f in FIELDS}

    def describe(self) -> list[dict[str, Any]]:
        """Every setting with its current value, in the order the Settings page shows them."""
        return [
            {
                "id": f.id,
                "group": f.group,
                "title": f.title,
                "description": f.description,
                "kind": f.kind,
                "options": [{"value": v, "label": label} for v, label in f.options],
                "minimum": f.minimum,
                "maximum": f.maximum,
                "unit": f.unit,
                "default": f.default,
                "value": self.get(f.id),
            }
            for f in FIELDS
        ]

    def update(self, values: dict[str, Any]) -> list[dict[str, Any]]:
        problems: list[str] = []
        clean: dict[str, Any] = {}
        for field_id, value in values.items():
            spec = BY_ID.get(field_id)
            if spec is None:
                problems.append(f"there is no setting {field_id!r}")
                continue
            if spec.kind == "integer" and isinstance(value, str) and value.strip().isdigit():
                value = int(value.strip())
            problem = self._valid(spec, value)
            if problem:
                problems.append(f"{spec.title}: {problem}")
            else:
                clean[field_id] = value
        if problems:
            raise InvalidSetting("; ".join(problems))
        now = utc_now().isoformat().replace("+00:00", "Z")
        with self._store.transaction() as conn:
            for field_id, value in clean.items():
                conn.execute(
                    """INSERT INTO preferences(key, value_json, updated_at) VALUES (?,?,?)
                       ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json,
                       updated_at = excluded.updated_at""",
                    (field_id, json.dumps(value), now),
                )
        return self.describe()

    @staticmethod
    def _valid(spec: SettingField, value: Any) -> str | None:
        if spec.kind == "choice":
            if value not in {v for v, _ in spec.options}:
                return f"{value!r} is not one of the choices"
            return None
        if spec.kind == "text":
            if not isinstance(value, str):
                return "needs text"
            if spec.maximum is not None and len(value) > spec.maximum:
                return f"at most {spec.maximum} characters"
            return None
        if not isinstance(value, int) or isinstance(value, bool):
            return "needs a whole number"
        if spec.minimum is not None and value < spec.minimum:
            return f"at least {spec.minimum}"
        if spec.maximum is not None and value > spec.maximum:
            return f"at most {spec.maximum}"
        return None
