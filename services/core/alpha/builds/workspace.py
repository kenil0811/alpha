"""Build workspaces: what the builder sees for one attempt.

    attempt-N/
      package/            the App package the builder edits (the template on attempt 1, the
                          previous attempt's package on a repair)
      reference/          APP_CONTRACT.md, SDK.md, UI_KIT.md (from the pinned UI profile)
      PLAN.md             the independent checks the candidate must pass (read-only intent)
      REPAIR.md           on a repair: every failed check with its evidence
      feedback/           screenshots from the failed checks the builder can look at

The builder may read the plan; the platform verifies against its own copy, so nothing written in
the workspace can change what is checked.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from alpha_contracts.verification import (
    CheckStatus,
    InvokeStep,
    RecordsStep,
    ValidationPlan,
    VerificationReport,
)

from alpha.builds.toolchain import PlatformResources
from alpha.execution.profiles import InstalledProfile

_IGNORE = shutil.ignore_patterns("__pycache__", ".DS_Store", "*.pyc")


@dataclass(frozen=True)
class TargetProfiles:
    runtime: InstalledProfile
    ui: InstalledProfile | None
    # The App identity the platform assigned (creation), or None to let the builder choose.
    app_id: str | None = None

    @property
    def sdk_version(self) -> str:
        pin = next(p for p in self.runtime.profile.packages if p.name == "alpha-sdk")
        return pin.version

    def ui_pin(self, name: str) -> str:
        assert self.ui is not None
        return next(p.version for p in self.ui.profile.packages if p.name == name)

    def identities(self) -> dict[str, str]:
        """The exact values a package's app.yaml must name."""
        found = {"runtime_profile": self.runtime.profile_id, "sdk_version": self.sdk_version}
        if self.app_id is not None:
            found["app_id"] = self.app_id
        if self.ui is not None:
            found |= {
                "ui_build_profile": self.ui.profile_id,
                "kit_version": self.ui_pin("@alpha/ui-kit"),
                "bridge_version": self.ui_pin("@alpha/ui-bridge"),
            }
        return found


def materialize(
    attempt_dir: Path,
    *,
    resources: PlatformResources,
    targets: TargetProfiles,
    plan: ValidationPlan,
    previous_package: Path | None,
    repair: str | None,
    feedback_files: list[Path],
) -> None:
    attempt_dir.mkdir(parents=True, exist_ok=False)
    package = attempt_dir / "package"
    if previous_package is not None and previous_package.is_dir():
        shutil.copytree(previous_package, package, ignore=_IGNORE, symlinks=False)
        template = package / "app.yaml.template"
        if template.is_file():  # a seed package names profiles by marker, like the template
            text = template.read_text(encoding="utf-8")
            for key, value in targets.identities().items():
                text = text.replace("{{" + key.upper() + "}}", value)
            (package / "app.yaml").write_text(text, encoding="utf-8")
            template.unlink()
    else:
        _copy_template(resources, targets, package, with_ui=plan.ui is not None)
    reference = attempt_dir / "reference"
    reference.mkdir()
    for source, name in (
        (resources.app_contract_reference, "APP_CONTRACT.md"),
        (resources.sdk_reference, "SDK.md"),
    ):
        if source.is_file():
            shutil.copyfile(source, reference / name)
    if targets.ui is not None:
        kit_reference = targets.ui.location / "node_modules" / "@alpha" / "ui-kit" / "REFERENCE.md"
        if kit_reference.is_file():
            shutil.copyfile(kit_reference, reference / "UI_KIT.md")
    (attempt_dir / "PLAN.md").write_text(render_plan(plan), encoding="utf-8")
    (attempt_dir / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    if repair:
        (attempt_dir / "REPAIR.md").write_text(repair, encoding="utf-8")
        feedback = attempt_dir / "feedback"
        feedback.mkdir()
        for file in feedback_files[:12]:
            if file.is_file():
                shutil.copyfile(file, feedback / file.name)


def _copy_template(
    resources: PlatformResources, targets: TargetProfiles, package: Path, *, with_ui: bool
) -> None:
    """The App template, with the platform's exact values filled in. The screen is included
    only when the plan checks one and a UI build profile is installed."""
    template = resources.app_template
    package.mkdir(parents=True)
    with_ui = with_ui and targets.ui is not None
    for area in ("src", "ui"):
        if (template / area).is_dir() and (area != "ui" or with_ui):
            shutil.copytree(template / area, package / area, ignore=_IGNORE)
    text = (template / "app.yaml.template").read_text(encoding="utf-8")
    for key, value in targets.identities().items():
        text = text.replace("{{" + key.upper() + "}}", value)
    if not with_ui:
        # No screen checked (or no UI build profile): the template becomes an App without one.
        data = yaml.safe_load(text)
        data.pop("ui", None)
        text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    (package / "app.yaml").write_text(text, encoding="utf-8")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def render_plan(plan: ValidationPlan) -> str:
    lines = [
        "# Independent checks for this App",
        "",
        "The platform runs these checks against the sealed package through real action runs and a",
        "real browser. They were written before the build; changing this file changes nothing.",
        '`{"$ref": "<step>.output.<key>"}` is a value an earlier step returned and',
        "`{\"$today\": n}` is today's date (plus n days) in the person's timezone.",
        "",
        "## Behaviour scenarios",
    ]
    for scenario in plan.scenarios:
        lines += ["", f"### {scenario.id}: {scenario.description}"]
        for step in scenario.steps:
            if isinstance(step, InvokeStep):
                want = f"must {step.expect[:-2] if step.expect == 'succeeded' else 'fail'}"
                if step.output is not None:
                    how = "exactly " if step.exact else "at least "
                    want += f" and return {how}{_json(step.output)}"
                call = f"run action `{step.action}` with `{_json(step.input)}`"
                lines.append(f"- `{step.id}`: {call}; it {want}.")
            elif isinstance(step, RecordsStep):
                parts = []
                if step.count is not None:
                    parts.append(f"exactly {step.count} record(s)")
                if step.includes:
                    parts.append(f"records including {_json(step.includes)}")
                where = (
                    f" matching `{_json(step.where.model_dump(by_alias=True))}`"
                    if step.where
                    else ""
                )
                lines.append(
                    f"- `{step.id}`: collection `{step.collection}`{where} must hold "
                    f"{' and '.join(parts) or 'records'} (read from storage, not from your output)."
                )
    if plan.ui is not None:
        ui = plan.ui
        lines += [
            "",
            "## The screen (ui/src/main.tsx)",
            "",
            "Primary interaction, performed in a real browser:",
        ]
        for ui_step in ui.primary:
            if ui_step.kind == "fill":
                lines.append(f'- type `{ui_step.text}` into the field labelled "{ui_step.label}"')
            elif ui_step.kind == "select":
                lines.append(f'- choose "{ui_step.text}" in the field labelled "{ui_step.label}"')
            elif ui_step.kind == "check":
                lines.append(f'- tick the checkbox labelled "{ui_step.label}"')
            elif ui_step.kind == "click":
                lines.append(f'- activate the button named "{ui_step.label}"')
            else:
                lines.append(f"- press {ui_step.key}")
        if ui.saved is not None:
            lines.append(
                f"- afterwards collection `{ui.saved.collection}` must hold "
                f"{_json(ui.saved.includes)} (saved through a declared ui action)"
            )
        for text in ui.shows:
            lines.append(f'- afterwards the screen shows "{text}"')
        if ui.seed:
            lines.append(
                "- sample data is then created by running "
                + ", ".join(f"`{s.action}` with `{_json(s.input)}`" for s in ui.seed)
            )
        for text in ui.seed_shows:
            lines.append(f'- with that data the screen shows "{text}"')
        lines += [
            "",
            "Also checked on every screen: it renders a page title (h1) with no script errors;",
            "an empty store shows no error; no sideways scrolling at 768px; when reading fails,",
            "an error (role=alert) is shown, not an empty screen; when saving fails, an error is",
            "shown, nothing is stored and the typed input is kept.",
        ]
    return "\n".join(lines) + "\n"


def render_repair(
    report: VerificationReport,
    attempt_number: int,
    remaining: int,
    *,
    timed_out_after: int | None = None,
) -> str:
    failed = [c for c in report.checks if c.status is CheckStatus.FAILED]
    skipped = [c for c in report.checks if c.status is CheckStatus.SKIPPED and c.required]
    if timed_out_after is not None:
        intro = [
            f"Attempt {attempt_number} ran out of time: the platform stops every attempt after "
            f"{max(1, round(timed_out_after / 60))} minutes, and it had not finished. package/",
            "holds what it wrote. Finish it: keep what already works, write only what is missing",
            "(check which files exist first), and keep the code small. The checks below ran on",
            "the unfinished package.",
        ]
    else:
        intro = [
            f"The candidate from attempt {attempt_number} failed independent checks. Fix the",
            "package in package/ so every check in PLAN.md passes. Do not work around a check;",
            "make the App behave as required.",
        ]
    lines = [
        f"# Repair request (attempt {attempt_number + 1})",
        "",
        *intro,
        f"Repairs left after this one: {remaining}.",
        "",
        "## Failed checks",
    ]
    for check in failed[:25]:
        lines += ["", f"### {check.id}", "", check.summary]
        detail = {
            k: v
            for k, v in check.detail.items()
            if k not in ("run_id",) and v not in (None, [], {})
        }
        if detail:
            text = json.dumps(detail, indent=2, ensure_ascii=False, default=str)
            lines += ["", "```json", text[:4000], "```"]
        if check.evidence:
            lines.append("")
            lines += [f"Screenshot: feedback/{Path(e).name}" for e in check.evidence]
    if skipped:
        lines += ["", "## Not run because of the failures above", ""]
        lines += [f"- {c.id}: {c.summary}" for c in skipped[:20]]
    for request in report.qualification_requests:
        lines += [
            "",
            f"Package `{request.package}` ({request.where}) is not available and will not be "
            "installed. Use the standard library or the SDK instead.",
        ]
    advisory = [c for c in report.checks if not c.required and c.status is CheckStatus.FAILED]
    for check in advisory:
        lines += ["", f"Also worth fixing ({check.id}): {check.summary}"]
    return "\n".join(lines) + "\n"


def evidence_files(report: VerificationReport, attempt_dir: Path) -> list[Path]:
    files: list[Path] = []
    for check in report.checks:
        if check.status is CheckStatus.FAILED:
            files += [attempt_dir / e for e in check.evidence]
    return files
