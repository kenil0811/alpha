"""BuilderHarness seam (specifications/contracts/Builder Harness Interface.md).

A harness turns a materialized build workspace plus brief into a candidate source package. It
runs inside the builder worker process, never in Core. It cannot seal or activate anything: it
reports normalized events and an outcome; Core decides authoritative build state afterwards.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from alpha_contracts.builds import (
    BuildDiagnostic,
    BuildRequest,
    BuildResultStatus,
    BuildUsage,
    FailureCategory,
)


@dataclass(frozen=True)
class HarnessCapabilities:
    name: str
    version: str
    cancel: bool
    resume: bool
    usage_reporting: bool
    structured_events: bool
    notes: tuple[str, ...] = ()


@dataclass
class HarnessInputs:
    """Everything the builder is allowed to see. Copied/synthetic context only; no live data."""

    request: BuildRequest
    workspace: Path
    goal: str
    instructions: str
    model: str
    # Interpreter of the App runtime profile the candidate must run on (for compile checks).
    candidate_python: Path
    # Exact profile identities the package must name: runtime_profile, sdk_version and, when a
    # UI profile is installed, ui_build_profile, kit_version, bridge_version.
    targets: dict[str, str] = field(default_factory=dict)
    fake_packages_dir: str | None = None
    # Which Claude sign-in the CLI uses: "oauth" (Alpha's), "api_key" or "cli" (its own login).
    claude_auth: str = "cli"


@dataclass
class HarnessEvent:
    kind: str
    payload: dict[str, Any]


@dataclass
class HarnessOutcome:
    status: BuildResultStatus
    usage: BuildUsage | None = None
    failure_category: FailureCategory | None = None
    diagnostics: list[BuildDiagnostic] = field(default_factory=list)
    final_text: str = ""
    exit_code: int | None = None


class HarnessSession(Protocol):
    session_ref: str


class BuilderHarness(Protocol):
    """Each implementation owns its concrete session type; the worker treats it as opaque."""

    def capabilities(self) -> HarnessCapabilities: ...

    def start(self, inputs: HarnessInputs) -> Any: ...

    def events(self, session: Any) -> Iterator[HarnessEvent]:
        """Yield normalized events until the harness process ends."""
        ...

    def cancel(self, session: Any) -> None: ...

    def result(self, session: Any) -> HarnessOutcome: ...
