"""Deterministic control harness. Proves lifecycle plumbing (events, failure, cancellation,
package handling, verification and repair); it can never prove generation quality and is never
a qualification route.

Modes, from the goal text `fake:<mode> [args]`:
- succeed               writes a valid pure App package (one computation action)
- package A [B ...]     copies test package A on attempt 1, B on attempt 2, ... (the last one
                        repeats); packages come from the host's ALPHA_FAKE_BUILDER_PACKAGES
- ... --claim-failed    (with `package`) writes the package but reports that it failed
- ... --wrong-app-id    (with `package`) ignores the App identity the platform assigned
- fail                  reports a harness error, writes nothing
- hang                  writes nothing and blocks until cancelled (spawns a descendant)
- broken_package        like succeed, but the handler is missing
- claims_success        writes nothing but says it succeeded (must not become a candidate)
- noisy                 like succeed, after writing more stderr than a pipe buffer holds
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import yaml
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

PURE_APP_YAML = """contract_version: '0.2'
app_id: {app_id}
name: Word statistics fixture
description: Deterministic control package produced by the fake harness.
runtime_profile: {runtime_profile}
sdk_version: {sdk_version}
primary_action: summarize
actions:
  - id: summarize
    title: Summarize text
    description: Count words and characters.
    handler: word_stats:summarize
    input_schema: {{type: object, required: [text], properties: {{text: {{type: string}}}}}}
    output_schema: {{type: object, required: [words, characters],
      properties: {{words: {{type: integer}}, characters: {{type: integer}}}}}}
    effect_class: none
    invocable_from: [assistant, manual]
    timeout_seconds: 10
    retry_class: pure
"""

PURE_HANDLER = (
    '"""Fake-harness fixture package."""\n\n'
    "def summarize(ctx, text: str) -> dict[str, int]:\n"
    "    words = [w for w in text.split() if w]\n"
    '    return {"words": len(words), "characters": len(text)}\n'
)


@dataclass
class FakeSession:
    session_ref: str
    mode: str
    args: list[str] = field(default_factory=list)
    child: subprocess.Popen[bytes] | None = None
    cancelled: bool = False
    workspace: Path = Path()
    inputs: HarnessInputs | None = None


class FakeHarness:
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
        words = inputs.goal.removeprefix("fake:").split() if inputs.goal.startswith("fake:") else []
        mode = words[0] if words else "succeed"
        return FakeSession(
            session_ref=f"fake-{os.getpid()}",
            mode=mode,
            args=words[1:],
            workspace=inputs.workspace,
            inputs=inputs,
        )

    def events(self, session: FakeSession) -> Iterator[HarnessEvent]:
        yield HarnessEvent("harness.started", {"harness": "fake", "mode": session.mode})
        package = session.workspace / "package"
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
        if session.mode == "noisy":
            # A chatty builder: 256 KiB of stderr. Core must drain it while the builder runs,
            # or the builder blocks on a full pipe until its deadline.
            for i in range(64):
                sys.stderr.write(f"builder log {i:02d} " + "." * 4080 + "\n")
            sys.stderr.write("noisy-end\n")
            sys.stderr.flush()
        if session.mode in ("succeed", "broken_package", "noisy"):
            yield from self._write_pure(session, package)
        elif session.mode == "package":
            yield from self._copy_package(session, package)
        yield HarnessEvent(
            "harness.assistant_text",
            {"text": "Done." if session.mode != "fail" else "I could not complete this."},
        )

    def _write_pure(self, session: FakeSession, package: Path) -> Iterator[HarnessEvent]:
        assert session.inputs is not None
        targets = session.inputs.targets
        shutil.rmtree(package, ignore_errors=True)
        files = {
            "app.yaml": PURE_APP_YAML.format(
                app_id=targets.get("app_id") or "fixture-word-stats",
                runtime_profile=targets.get("runtime_profile"),
                sdk_version=targets.get("sdk_version"),
            ),
            "src/word_stats.py": PURE_HANDLER
            if session.mode != "broken_package"
            else "# handler deliberately missing\n",
        }
        for relative, content in files.items():
            path = package / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            yield HarnessEvent(
                "harness.file_written",
                {"path": relative, "sha256": hashlib.sha256(content.encode()).hexdigest()},
            )
        # Real builders leave bytecode caches behind; they never become part of a Version.
        cache = package / "src" / "__pycache__"
        cache.mkdir(exist_ok=True)
        (cache / "word_stats.cpython-313.pyc").write_bytes(b"\x00residue")

    def _copy_package(self, session: FakeSession, package: Path) -> Iterator[HarnessEvent]:
        assert session.inputs is not None
        names = [a for a in session.args if not a.startswith("--")]
        root = session.inputs.fake_packages_dir
        if not names or root is None:
            yield HarnessEvent("harness.error", {"message": "no fake package source configured"})
            return
        number = session.inputs.request.attempt_number
        name = names[min(number, len(names)) - 1]
        source = Path(root) / name
        # Like a builder following its workspace: a compiled screen only when the plan checks
        # one and a UI build profile is installed (the template itself declares no `ui`).
        plan_file = session.workspace / "plan.json"
        plan = json.loads(plan_file.read_text(encoding="utf-8")) if plan_file.is_file() else {}
        with_ui = plan.get("ui") is not None and "ui_build_profile" in session.inputs.targets
        shutil.rmtree(package, ignore_errors=True)
        shutil.copytree(source, package)
        if not with_ui:
            shutil.rmtree(package / "ui", ignore_errors=True)
        template = package / "app.yaml.template"
        if template.exists():
            text = template.read_text(encoding="utf-8")
            for key, value in session.inputs.targets.items():
                text = text.replace("{{" + key.upper() + "}}", str(value))
            app_id = session.inputs.targets.get("app_id")
            if app_id and "--wrong-app-id" in session.args:
                app_id = f"{app_id}-other"
            if app_id:  # a builder keeps the identity the platform assigned
                text = re.sub(r"(?m)^app_id: .*$", f'app_id: "{app_id}"', text)
            if not with_ui:
                data = yaml.safe_load(text)
                data.pop("ui", None)
                text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
            (package / "app.yaml").write_text(text, encoding="utf-8")
            template.unlink()
        yield HarnessEvent("harness.package_copied", {"package": name, "attempt": number})

    def cancel(self, session: FakeSession) -> None:
        session.cancelled = True
        if session.child is not None:
            session.child.kill()

    def result(self, session: FakeSession) -> HarnessOutcome:
        usage = BuildUsage(cost_basis=CostBasis.UNAVAILABLE, turns=1)
        if session.cancelled:
            return HarnessOutcome(BuildResultStatus.CANCELLED, usage, FailureCategory.CANCELLED)
        if session.mode == "fail" or "--claim-failed" in session.args:
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
