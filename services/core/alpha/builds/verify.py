"""Candidate verification pipeline (Current Release Specification §3–§4, Blueprint §6).

Stages, in order; a failed stage leaves every later required check `skipped`, which blocks
readiness exactly like a failure:

1. package    layout and file rules, the App contract, JSON Schemas
2. deps       exact runtime/SDK/UI profiles re-verified on disk; extra packages become
              qualification requests
3. seal       UI compiled by the trusted tool, Version sealed with digests and lock provenance
4. handlers   imports scanned and handlers bound in a disposable worker on the exact profile
5. behavior   independent scenarios through real runs in fresh previews
6. ui         the sealed screen driven in a headless browser: empty, primary interaction,
              populated, failed read and failed save
7. tests      the candidate's own tests (supplementary, never required)

The report's verdict is derived from its checks by the contract itself.
"""

from __future__ import annotations

import platform
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from alpha_contracts.apps import AppSource
from alpha_contracts.builds import BuildResultStatus
from alpha_contracts.verification import (
    CheckResult,
    CheckStatus,
    DependencyQualificationRequest,
    ValidationPlan,
    VerificationReport,
)

from alpha.builds.plan import run_model_failures, run_scenario
from alpha.builds.preview import PreviewDeps, PreviewPlatform
from alpha.builds.ui_check import UiRenderCheck
from alpha.capabilities.errors import OperationFailed
from alpha.data.packages import (
    ResolvedDependencies,
    SealedPackage,
    UiBuildFailed,
    UnsupportedDependencies,
    collect_files,
    load_source,
    resolve_dependencies,
    seal,
)
from alpha.execution.app_runs import HandlerBinder
from alpha.solutions.registry import AppRegistry, interpret_handler_report

STAGES = ("package", "deps", "seal", "handlers", "behavior", "ui")


@dataclass
class VerificationOutcome:
    report: VerificationReport
    sealed: SealedPackage | None
    handler_report: dict[str, Any] | None = None


def _result(
    check_id: str,
    stage: str,
    ok: bool,
    summary: str,
    detail: dict[str, Any] | None = None,
) -> CheckResult:
    return CheckResult(
        id=check_id,
        stage=stage,
        status=CheckStatus.PASSED if ok else CheckStatus.FAILED,
        summary=summary[:1000],
        detail=detail or {},
    )


def _stage_ok(run: _Run, stage: str) -> bool:
    """Every required check of the stage passed. An advisory check that was skipped (such as
    model.failure.<action> when no planned step makes the action call the model) does not hold
    back the next stage. Found in M1-R07: it did, so the screen was never checked and no attempt
    of an App with an unexercised model action could pass."""
    return all(
        c.status is CheckStatus.PASSED for c in run.checks if c.stage == stage and c.required
    )


def _skipped(check_id: str, stage: str, summary: str) -> CheckResult:
    return CheckResult(id=check_id, stage=stage, status=CheckStatus.SKIPPED, summary=summary)


def _failure_detail(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, OperationFailed):
        return {"code": exc.code, **exc.details}
    if isinstance(exc, UiBuildFailed):
        return {"log_tail": exc.log[-3000:]}
    return {"error": f"{type(exc).__name__}: {exc}"[:500]}


def _message(exc: Exception) -> str:
    return exc.message if isinstance(exc, OperationFailed) else str(exc)


def _requests_detail(requests: list[DependencyQualificationRequest]) -> dict[str, Any]:
    return {"qualification_requests": [r.model_dump() for r in requests]}


class Stopped(Exception):
    """The build was cancelled or Core is quitting; verification ends without a verdict."""


@dataclass
class _Run:
    """One verification in progress: what is known so far and every check recorded."""

    build_id: str
    attempt_id: str
    attempt_number: int
    lineage: list[str]
    builder_status: BuildResultStatus
    package_dir: Path
    attempt_dir: Path
    plan: ValidationPlan
    expected_app_id: str | None
    on_check: Callable[[CheckResult], None] | None
    stop: threading.Event | None
    checks: list[CheckResult] = field(default_factory=list)
    requests: list[DependencyQualificationRequest] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    reached: str = "package"
    source: AppSource | None = None
    files: list[Path] = field(default_factory=list)
    deps: ResolvedDependencies | None = None
    sealed: SealedPackage | None = None
    handler_report: dict[str, Any] | None = None

    def add(self, result: CheckResult) -> bool:
        if self.stop is not None and self.stop.is_set():
            raise Stopped()
        self.checks.append(result)
        if self.on_check is not None:
            self.on_check(result)
        return result.status is CheckStatus.PASSED

    @property
    def has_ui(self) -> bool:
        """A compiled custom screen that the headless render check drives."""
        if self.source is not None:
            return self.source.ui is not None and self.source.ui.entry is not None
        return (self.package_dir / "ui").is_dir()

    @property
    def has_screen(self) -> bool:
        """Anything the shell can draw: a declarative screen or a custom ui entry."""
        if self.source is not None:
            return self.source.has_screen()
        return (self.package_dir / "ui").is_dir()

    def finish(self, supplementary: list[CheckResult] | None = None) -> VerificationOutcome:
        """Mark every stage after the last one reached as not run, then derive the report."""
        for stage in STAGES[STAGES.index(self.reached) + 1 :]:
            if stage != "ui" or self.has_ui:
                self.add(
                    _skipped(
                        f"{stage}.not_run", stage, f"not run: the {self.reached} stage did not pass"
                    )
                )
        sealed = self.sealed
        package_sha = sealed.package_sha256 if sealed else None
        manifest = sealed.dependency_manifest if sealed else None
        report = VerificationReport(
            build_id=self.build_id,
            attempt_id=self.attempt_id,
            attempt_number=self.attempt_number,
            lineage=self.lineage,
            builder_status=self.builder_status,
            package_sha256=package_sha,
            version_id=sealed.version_id if sealed else None,
            dependency_manifest_sha256=sealed.dependency_manifest_sha256 if sealed else None,
            runtime_profile_id=manifest.runtime_profile_id if manifest else None,
            ui_build_profile_id=manifest.ui_build.profile_id
            if manifest and manifest.ui_build
            else None,
            environment=self.environment,
            checks=self.checks,
            supplementary=supplementary or [],
            qualification_requests=self.requests,
            unresolved_limits=["App and builder processes are not yet OS-sandboxed (F20)"],
            passed=VerificationReport.verdict_of(self.builder_status, package_sha, self.checks),
        )
        return VerificationOutcome(report, sealed, self.handler_report)


class CandidateVerifier:
    def __init__(
        self,
        registry: AppRegistry,
        binder: HandlerBinder,
        preview_deps: PreviewDeps,
        ui_check: UiRenderCheck | None,
        ui_builder: Callable[..., dict[str, Any]] | None,
    ) -> None:
        self._registry = registry
        self._binder = binder
        self._preview_deps = preview_deps
        self._ui_check = ui_check
        self._ui_builder = ui_builder

    def verify(
        self,
        *,
        build_id: str,
        attempt_id: str,
        attempt_number: int,
        lineage: list[str],
        builder_status: BuildResultStatus,
        package_dir: Path,
        attempt_dir: Path,
        plan: ValidationPlan,
        expected_app_id: str | None = None,
        on_check: Callable[[CheckResult], None] | None = None,
        stop: threading.Event | None = None,
    ) -> VerificationOutcome | None:
        """Run every stage in order; None when stopped (cancel or quit) before a verdict."""
        run = _Run(
            build_id,
            attempt_id,
            attempt_number,
            lineage,
            builder_status,
            package_dir,
            attempt_dir,
            plan,
            expected_app_id,
            on_check,
            stop,
            environment={
                "os": f"{platform.system()} {platform.release()} {platform.machine()}",
                "core_python": sys.version.split()[0],
            },
        )
        try:
            for stage in (self._package, self._deps, self._seal, self._handlers):
                if not stage(run):
                    return run.finish()
            self._behaviour(run)
            self._ui(run)
            return run.finish(self._candidate_tests(run))
        except Stopped:
            return None

    # ----- stages: each returns whether verification continues -------------------------

    def _package(self, run: _Run) -> bool:
        try:
            run.source = load_source(run.package_dir)
        except Exception as exc:
            return run.add(
                _result("package.contract", "package", False, _message(exc), _failure_detail(exc))
            )
        run.add(
            _result("package.contract", "package", True, f"app.yaml declares {run.source.app_id}")
        )
        if run.expected_app_id is not None:
            if run.source.app_id != run.expected_app_id:
                summary = (
                    f"app.yaml declares app_id {run.source.app_id!r}; this App's identity is "
                    f"{run.expected_app_id!r} and cannot change"
                )
                return run.add(_result("package.identity", "package", False, summary))
            run.add(
                _result(
                    "package.identity", "package", True, "app_id is the identity Alpha assigned"
                )
            )
        if run.source.screen is not None:
            tabs = ", ".join(t.title for t in run.source.screen.tabs)
            first = run.source.screen.tabs[0].blocks[0]
            # The conventions: the person lands on the data or the way in, never on a summary.
            if run.plan.ui is not None and first.kind not in (
                "quick_entry",
                "form",
                "table",
                "board",
                "list",
            ):
                return run.add(
                    _result(
                        "package.screen",
                        "package",
                        False,
                        "the first tab must open on the data or the way in: its first block is "
                        f"a {first.kind}, not a table, board, list, quick_entry or form",
                    )
                )
            run.add(
                _result(
                    "package.screen",
                    "package",
                    True,
                    f"Alpha draws its screen: {tabs}",
                )
            )
        elif run.source.ui is None or run.source.ui.entry is None:
            # Without its own screen, Alpha runs the App from one form (M1 review finding F03).
            if run.source.primary_action is None:
                return run.add(
                    _result(
                        "package.primary_action",
                        "package",
                        False,
                        "an App without its own screen must name primary_action: the one action "
                        "a person runs to get its result (keep helper steps off the manual list)",
                    )
                )
            run.add(
                _result(
                    "package.primary_action",
                    "package",
                    True,
                    f"people run {run.source.primary_action} to get the result",
                )
            )
        try:
            run.files = collect_files(run.package_dir, run.source)
        except Exception as exc:
            return run.add(
                _result("package.layout", "package", False, _message(exc), _failure_detail(exc))
            )
        return run.add(
            _result(
                "package.layout", "package", True, f"{len(run.files)} file(s) follow the layout"
            )
        )

    def _deps(self, run: _Run) -> bool:
        run.reached = "deps"
        assert run.source is not None
        try:
            deps = resolve_dependencies(run.source, self._registry.inventory)
        except UnsupportedDependencies as exc:
            run.requests += exc.requests
            summary = (
                "the package needs packages outside the qualified runtime profile: "
                + ", ".join(r.package for r in exc.requests)
            )
            return run.add(
                _result("deps.profiles", "deps", False, summary, _requests_detail(exc.requests))
            )
        except Exception as exc:
            return run.add(
                _result("deps.profiles", "deps", False, _message(exc), _failure_detail(exc))
            )
        run.deps = deps
        run.environment |= {
            "runtime_profile": deps.runtime.profile_id,
            "python": str(deps.runtime.profile.target.python_version),
            "sdk": deps.sdk.version,
        }
        if deps.ui is not None:
            run.environment["ui_build_profile"] = deps.ui.profile_id
        ui = f", UI {deps.ui.profile_id}" if deps.ui else ""
        return run.add(
            _result(
                "deps.profiles",
                "deps",
                True,
                f"runtime {deps.runtime.profile_id}, SDK {deps.sdk.version}{ui}",
            )
        )

    def _seal(self, run: _Run) -> bool:
        run.reached = "seal"
        assert run.source is not None and run.deps is not None
        started = time.monotonic()
        try:
            sealed = seal(
                run.package_dir,
                run.source,
                run.deps,
                run.files,
                run.attempt_dir / "version",
                self._ui_builder,
            )
        except UiBuildFailed as exc:
            return run.add(
                _result(
                    "seal.ui_build",
                    "seal",
                    False,
                    f"the UI did not compile: {exc}",
                    _failure_detail(exc),
                )
            )
        except Exception as exc:
            return run.add(
                _result("seal.package", "seal", False, _message(exc), _failure_detail(exc))
            )
        run.sealed = sealed
        if sealed.ui_build is not None:
            profile = run.deps.ui.profile_id if run.deps.ui else "?"
            size = sealed.ui_build.get("output", {}).get("html_bytes")
            run.add(
                _result(
                    "seal.ui_build",
                    "seal",
                    True,
                    f"UI compiled against {profile} ({size} bytes)",
                    {"modules": sealed.ui_build.get("modules"), "csp": sealed.ui_build.get("csp")},
                )
            )
        elapsed = time.monotonic() - started
        return run.add(
            _result(
                "seal.package",
                "seal",
                True,
                f"sealed {sealed.version_id} ({len(sealed.index.files)} files) in {elapsed:.1f}s",
                {"package_sha256": sealed.package_sha256},
            )
        )

    def _handlers(self, run: _Run) -> bool:
        """Imports scanned and handlers bound in a disposable worker on the exact profile."""
        run.reached = "handlers"
        assert run.source is not None and run.deps is not None and run.sealed is not None
        try:
            report = self._binder.validate_handlers(run.sealed.path, run.source, run.deps.runtime)
        except Exception as exc:
            return run.add(
                _result("handlers.bind", "handlers", False, _message(exc), _failure_detail(exc))
            )
        run.handler_report = report
        imports = report.get("imports") or {}
        allowed = "imports are the standard library, the SDK and the package's own modules"
        try:
            interpret_handler_report(report, run.source, run.deps.runtime.profile_id)
        except UnsupportedDependencies as exc:
            run.requests += exc.requests
            found = ", ".join(f"{r.package} ({r.where})" for r in exc.requests)
            summary = f"the code imports packages that are not in the runtime profile: {found}"
            return run.add(
                _result(
                    "handlers.imports", "handlers", False, summary, _requests_detail(exc.requests)
                )
            )
        except OperationFailed as exc:
            if not imports.get("ok"):
                problems = "; ".join((imports.get("problems") or [])[:3])
                summary = f"{_message(exc)}: {problems}"
                return run.add(
                    _result("handlers.imports", "handlers", False, summary, {"imports": imports})
                )
            run.add(_result("handlers.imports", "handlers", True, allowed, {"imports": imports}))
            reasons = [
                f"{a.get('id')} ({a.get('handler')}): {'; '.join(a.get('problems', []))}"
                for a in report.get("actions") or []
                if not a.get("ok")
            ]
            summary = _message(exc) + (f": {' | '.join(reasons[:3])}" if reasons else "")
            return run.add(
                _result("handlers.bind", "handlers", False, summary, _failure_detail(exc))
            )
        detail = {"stdlib": imports.get("stdlib"), "local": imports.get("local")}
        run.add(_result("handlers.imports", "handlers", True, allowed, detail))
        bound = f"{len(run.source.actions)} handler(s) bound on {run.deps.runtime.profile_id}"
        return run.add(
            _result("handlers.bind", "handlers", True, bound, {"actions": report.get("actions")})
        )

    def _preview(self, run: _Run, name: str) -> PreviewPlatform:
        return PreviewPlatform(run.attempt_dir / "preview" / name, self._preview_deps)

    def _install(self, run: _Run, preview: PreviewPlatform) -> None:
        assert run.sealed is not None and run.handler_report is not None
        preview.install(run.sealed, run.handler_report)

    def _behaviour(self, run: _Run) -> None:
        """Independent scenarios, each in a fresh preview, judged by reading storage."""
        run.reached = "behavior"
        for scenario in run.plan.scenarios:
            results = run_scenario(
                lambda name: self._preview(run, name),
                lambda preview: self._install(run, preview),
                scenario,
            )
            for result in results:
                run.add(result)
        # Actions that use model estimates must stay honest when the model fails (F04).
        scenarios_ok = _stage_ok(run, "behavior")
        assert run.source is not None
        model_actions = [a.id for a in run.source.actions if "models" in a.capability_requirements]
        if model_actions and scenarios_ok:
            for result in run_model_failures(
                lambda name: self._preview(run, name),
                lambda preview: self._install(run, preview),
                run.plan,
                model_actions,
            ):
                run.add(result)
        elif model_actions:
            for action in model_actions:
                run.add(
                    _skipped(
                        f"model.failure.{action}",
                        "behavior",
                        "not run: the behaviour checks did not pass",
                    )
                )

    def _ui(self, run: _Run) -> None:
        """The sealed screen, driven in the pinned headless browser."""
        behaviour_ok = _stage_ok(run, "behavior")
        run.reached = "ui"
        if not run.has_ui:
            return
        if not behaviour_ok:
            run.add(_skipped("ui.not_run", "ui", "not run: the behaviour checks did not pass"))
            return
        if self._ui_check is None:
            run.add(_skipped("ui.render", "ui", "no UI render check is configured on this Mac"))
            return
        preview = self._preview(run, "ui")
        try:
            self._install(run, preview)
            ui_checks, ui_env = self._ui_check.run(
                preview,
                run.plan.ui,
                run.attempt_dir / "evidence" / "ui",
                "evidence/ui",
                stop=run.stop,
            )
        finally:
            preview.close()
        for result in ui_checks:
            run.add(result)
        run.environment |= {f"ui_{k}": v for k, v in ui_env.items()}

    def _candidate_tests(self, run: _Run) -> list[CheckResult]:
        """The package's own tests: supplementary evidence, never required."""
        assert run.sealed is not None and run.deps is not None
        tests = self._binder.run_candidate_tests(run.sealed.path, run.deps.runtime)
        if not tests.get("present"):
            return []
        outcome = "all passed" if tests.get("ok") else "some failed"
        return [
            CheckResult(
                id="candidate_tests",
                stage="tests",
                required=False,
                status=CheckStatus.PASSED if tests.get("ok") else CheckStatus.FAILED,
                summary=f"{tests.get('ran', 0)} candidate test(s); {outcome} "
                "(supplementary, not acceptance evidence)",
                detail=tests,
            )
        ]
