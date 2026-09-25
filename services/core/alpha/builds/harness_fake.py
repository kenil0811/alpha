"""Deterministic control harness. Proves lifecycle plumbing (events, failure, cancellation,
package handling); it can never prove generation quality and is never a qualification route."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass

from alpha_contracts.builds import (
    BuildDiagnostic,
    BuildResultStatus,
    BuildUsage,
    CostBasis,
    FailureCategory,
)

from alpha.builds.harness import (
    HarnessCapabilities,
    HarnessEvent,
    HarnessInputs,
    HarnessOutcome,
)

FAKE_PACKAGE = {
    "app.yaml": (
        "contract_version: '0.2'\n"
        "app_id: fixture_word_stats\n"
        "name: Word statistics fixture\n"
        "description: Deterministic control package produced by the fake harness.\n"
        "runtime_profile: platform-runtime-3.13.9\n"
        "sdk_version: none\n"
        "actions:\n"
        "  - id: summarize\n"
        "    title: Summarize text\n"
        "    description: Count words and characters.\n"
        "    handler: word_stats:summarize\n"
        "    input_schema: {type: object, required: [text], properties: {text: {type: string}}}\n"
        "    output_schema: {type: object, required: [words, characters],\n"
        "      properties: {words: {type: integer}, characters: {type: integer}}}\n"
        "    capability_requirements: []\n"
        "    effect_class: none\n"
        "    invocable_from: [assistant]\n"
        "    timeout_seconds: 10\n"
        "    retry_class: pure\n"
    ),
    "src/word_stats.py": (
        '"""Fake-harness fixture package."""\n\n'
        "def summarize(text: str) -> dict[str, int]:\n"
        "    words = [w for w in text.split() if w]\n"
        '    return {"words": len(words), "characters": len(text)}\n'
    ),
}


@dataclass
class FakeSession:
    session_ref: str
    mode: str
    child: subprocess.Popen[bytes] | None = None
    cancelled: bool = False


class FakeHarness:
    """Modes (taken from the goal text prefix `fake:<mode>`):
    - succeed        writes a valid pure package
    - fail           reports a harness error, writes nothing
    - hang           writes nothing and blocks until cancelled (spawns a descendant)
    - broken_package writes a package whose handler is missing
    - claims_success writes nothing but says it succeeded (must not become a candidate)
    """

    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities(
            name="fake",
            version="0",
            cancel=True,
            resume=False,
            usage_reporting=False,
            structured_events=True,
            notes=("control fixture only; proves lifecycle, never generation",),
        )

    def start(self, inputs: HarnessInputs) -> FakeSession:
        mode = (
            inputs.goal.removeprefix("fake:").split()[0]
            if inputs.goal.startswith("fake:")
            else "succeed"
        )
        session = FakeSession(session_ref=f"fake-{os.getpid()}", mode=mode)
        session.workspace = inputs.workspace  # type: ignore[attr-defined]
        return session

    def events(self, session: FakeSession) -> Iterator[HarnessEvent]:
        workspace = session.workspace  # type: ignore[attr-defined]
        yield HarnessEvent("harness.started", {"harness": "fake", "mode": session.mode})
        if session.mode == "hang":
            session.child = subprocess.Popen(
                ["/bin/sleep", "600"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            yield HarnessEvent(
                "harness.tool_use", {"tool": "sleep", "child_pid": session.child.pid}
            )
            while not session.cancelled:
                time.sleep(0.2)
            return
        if session.mode in ("succeed", "broken_package"):
            for relative, content in FAKE_PACKAGE.items():
                if session.mode == "broken_package" and relative.startswith("src/"):
                    content = "# handler deliberately missing\n"
                path = workspace / "package" / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                yield HarnessEvent(
                    "harness.file_written",
                    {"path": relative, "sha256": hashlib.sha256(content.encode()).hexdigest()},
                )
        yield HarnessEvent(
            "harness.assistant_text",
            {"text": "Done." if session.mode != "fail" else "I could not complete this."},
        )

    def cancel(self, session: FakeSession) -> None:
        session.cancelled = True
        if session.child is not None:
            session.child.kill()

    def result(self, session: FakeSession) -> HarnessOutcome:
        usage = BuildUsage(cost_basis=CostBasis.UNAVAILABLE, turns=1)
        if session.cancelled:
            return HarnessOutcome(BuildResultStatus.CANCELLED, usage, FailureCategory.CANCELLED)
        if session.mode == "fail":
            return HarnessOutcome(
                BuildResultStatus.FAILED,
                usage,
                FailureCategory.HARNESS_ERROR,
                [
                    BuildDiagnostic(
                        level="error", code="fake_failure", message="synthetic harness failure"
                    )
                ],
            )
        # `claims_success` returns candidate without writing a package: Core must reject it.
        return HarnessOutcome(BuildResultStatus.CANDIDATE, usage, final_text="Done.")


def _self_test() -> None:  # pragma: no cover - manual aid
    print(json.dumps(FAKE_PACKAGE, indent=1), file=sys.stderr)
