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

from alpha_contracts.builds import BuildResultStatus
from alpha_contracts.verification import (
    CheckResult,
    CheckStatus,
    DependencyQualificationRequest,
    ValidationPlan,
    VerificationReport,
)

from alpha.builds.plan import run_scenario
from alpha.builds.preview import PreviewDeps, PreviewPlatform
from alpha.builds.ui_check import UiRenderCheck
from alpha.capabilities.errors import OperationFailed
from alpha.data.apps import AppRegistry, interpret_handler_report
from alpha.data.packages import (
    SealedPackage,
    UiBuildFailed,
    UnsupportedDependencies,
    collect_files,
    load_source,
    resolve_dependencies,
    seal,
)
from alpha.execution.app_runs import HandlerBinder

STAGES = ("package", "deps", "seal", "handlers", "behavior", "ui")


@dataclass
class VerificationOutcome:
    report: VerificationReport
    sealed: SealedPackage | None
    handler_report: dict[str, Any] | None = None
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)


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


def _failure_detail(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, OperationFailed):
        return {"code": exc.code, **exc.details}
    if isinstance(exc, UiBuildFailed):
        return {"log_tail": exc.log[-3000:]}
    return {"error": f"{type(exc).__name__}: {exc}"[:500]}


def _message(exc: Exception) -> str:
    return exc.message if isinstance(exc, OperationFailed) else str(exc)


class Stopped(Exception):
    """The build was cancelled or Core is quitting; verification ends without a verdict."""


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

    def verify(self, **kwargs: Any) -> VerificationOutcome | None:
        """Run the pipeline; None when stopped (cancel or quit) before a verdict."""
        try:
            return self._verify(**kwargs)
        except Stopped:
            return None

    def _verify(
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
        on_check: Callable[[CheckResult], None] | None = None,
        stop: threading.Event | None = None,
    ) -> VerificationOutcome:
        checks: list[CheckResult] = []
        requests: list[DependencyQualificationRequest] = []
        environment = {
            "os": f"{platform.system()} {platform.release()} {platform.machine()}",
            "core_python": sys.version.split()[0],
        }
        sealed: SealedPackage | None = None
        handler_report: dict[str, Any] | None = None
        reached = "package"

        def add(result: CheckResult) -> bool:
            if stop is not None and stop.is_set():
                raise Stopped()
            checks.append(result)
            if on_check is not None:
                on_check(result)
            return result.status is CheckStatus.PASSED

        def finish(supplementary: list[CheckResult] | None = None) -> VerificationOutcome:
            for stage in STAGES[STAGES.index(reached) + 1 :]:
                if stage == "ui" and not self._has_ui(sealed, package_dir):
                    continue
                add(
                    CheckResult(
                        id=f"{stage}.not_run",
                        stage=stage,
                        status=CheckStatus.SKIPPED,
                        summary=f"not run: the {reached} stage did not pass",
                    )
                )
            package_sha = sealed.package_sha256 if sealed else None
            report = VerificationReport(
                build_id=build_id,
                attempt_id=attempt_id,
                attempt_number=attempt_number,
                lineage=lineage,
                builder_status=builder_status,
                package_sha256=package_sha,
                version_id=sealed.version_id if sealed else None,
                dependency_manifest_sha256=sealed.dependency_manifest_sha256 if sealed else None,
                runtime_profile_id=sealed.dependency_manifest.runtime_profile_id
                if sealed
                else None,
                ui_build_profile_id=(
                    sealed.dependency_manifest.ui_build.profile_id
                    if sealed and sealed.dependency_manifest.ui_build
                    else None
                ),
                environment=environment,
                checks=checks,
                supplementary=supplementary or [],
                qualification_requests=requests,
                unresolved_limits=[
                    "App and builder processes are not yet OS-sandboxed (F20)",
                ],
                passed=VerificationReport.verdict_of(builder_status, package_sha, checks),
            )
            return VerificationOutcome(report, sealed, handler_report)

        # 1. package: contract, files
        try:
            source = load_source(package_dir)
        except Exception as exc:
            add(_result("package.contract", "package", False, _message(exc), _failure_detail(exc)))
            return finish()
        add(_result("package.contract", "package", True, f"app.yaml declares {source.app_id}"))
        try:
            files = collect_files(package_dir, source)
        except Exception as exc:
            add(_result("package.layout", "package", False, _message(exc), _failure_detail(exc)))
            return finish()
        add(_result("package.layout", "package", True, f"{len(files)} file(s) follow the layout"))

        # 2. deps
        reached = "deps"
        try:
            deps = resolve_dependencies(source, self._registry.inventory)
        except UnsupportedDependencies as exc:
            requests += exc.requests
            add(
                _result(
                    "deps.profiles",
                    "deps",
                    False,
                    "the package needs packages outside the qualified runtime profile: "
                    + ", ".join(r.package for r in exc.requests),
                    {"qualification_requests": [r.model_dump() for r in exc.requests]},
                )
            )
            return finish()
        except Exception as exc:
            add(_result("deps.profiles", "deps", False, _message(exc), _failure_detail(exc)))
            return finish()
        add(
            _result(
                "deps.profiles",
                "deps",
                True,
                f"runtime {deps.runtime.profile_id}, SDK {deps.sdk.version}"
                + (f", UI {deps.ui.profile_id}" if deps.ui else ""),
            )
        )
        environment |= {
            "runtime_profile": deps.runtime.profile_id,
            "python": str(deps.runtime.profile.target.python_version),
            "sdk": deps.sdk.version,
        }
        if deps.ui is not None:
            environment["ui_build_profile"] = deps.ui.profile_id

        # 3. seal (includes the UI build)
        reached = "seal"
        try:
            started = time.monotonic()
            sealed = seal(
                package_dir, source, deps, files, attempt_dir / "version", self._ui_builder
            )
        except UiBuildFailed as exc:
            add(
                _result(
                    "seal.ui_build",
                    "seal",
                    False,
                    f"the UI did not compile: {exc}",
                    _failure_detail(exc),
                )
            )
            return finish()
        except Exception as exc:
            add(_result("seal.package", "seal", False, _message(exc), _failure_detail(exc)))
            return finish()
        if sealed.ui_build is not None:
            add(
                _result(
                    "seal.ui_build",
                    "seal",
                    True,
                    f"UI compiled against {deps.ui.profile_id if deps.ui else '?'} "
                    f"({sealed.ui_build.get('output', {}).get('html_bytes')} bytes)",
                    {"modules": sealed.ui_build.get("modules"), "csp": sealed.ui_build.get("csp")},
                )
            )
        add(
            _result(
                "seal.package",
                "seal",
                True,
                f"sealed {sealed.version_id} ({len(sealed.index.files)} files) in "
                f"{time.monotonic() - started:.1f}s",
                {"package_sha256": sealed.package_sha256},
            )
        )

        # 4. handlers: imports and bindings on the exact profile
        reached = "handlers"
        try:
            handler_report = self._binder.validate_handlers(sealed.path, source, deps.runtime)
        except Exception as exc:
            add(_result("handlers.bind", "handlers", False, _message(exc), _failure_detail(exc)))
            return finish()
        imports = handler_report.get("imports") or {}
        try:
            interpret_handler_report(handler_report, source, deps.runtime.profile_id)
        except UnsupportedDependencies as exc:
            requests += exc.requests
            add(
                _result(
                    "handlers.imports",
                    "handlers",
                    False,
                    "the code imports packages that are not in the runtime profile: "
                    + ", ".join(f"{r.package} ({r.where})" for r in exc.requests),
                    {"qualification_requests": [r.model_dump() for r in exc.requests]},
                )
            )
            return finish()
        except OperationFailed as exc:
            ok_imports = bool(imports.get("ok"))
            problems = imports.get("problems") or []
            add(
                _result(
                    "handlers.imports",
                    "handlers",
                    ok_imports,
                    "imports are the standard library, the SDK and the package's own modules"
                    if ok_imports
                    else f"{_message(exc)}: {'; '.join(problems[:3])}",
                    {"imports": imports},
                )
            )
            if ok_imports:
                reasons = [
                    f"{a.get('id')} ({a.get('handler')}): {'; '.join(a.get('problems', []))}"
                    for a in handler_report.get("actions") or []
                    if not a.get("ok")
                ]
                summary = _message(exc) + (f": {' | '.join(reasons[:3])}" if reasons else "")
                add(_result("handlers.bind", "handlers", False, summary, _failure_detail(exc)))
            return finish()
        add(
            _result(
                "handlers.imports",
                "handlers",
                True,
                "imports are the standard library, the SDK and the package's own modules",
                {"stdlib": imports.get("stdlib"), "local": imports.get("local")},
            )
        )
        add(
            _result(
                "handlers.bind",
                "handlers",
                True,
                f"{len(source.actions)} handler(s) bound on {deps.runtime.profile_id}",
                {"actions": handler_report.get("actions")},
            )
        )

        # 5. behavior: independent scenarios in fresh previews
        reached = "behavior"
        previews = attempt_dir / "preview"

        def make_preview(name: str) -> PreviewPlatform:
            return PreviewPlatform(previews / name, self._preview_deps)

        def install(preview: PreviewPlatform) -> None:
            assert sealed is not None and handler_report is not None
            preview.install(sealed, handler_report)

        for scenario in plan.scenarios:
            for result in run_scenario(make_preview, install, scenario):
                add(result)
        behaviour_ok = all(c.status is CheckStatus.PASSED for c in checks if c.stage == "behavior")

        # 6. ui
        if source.ui is not None and source.ui.entry is not None:
            reached = "ui"
            if not behaviour_ok:
                add(
                    CheckResult(
                        id="ui.not_run",
                        stage="ui",
                        status=CheckStatus.SKIPPED,
                        summary="not run: the behaviour checks did not pass",
                    )
                )
            elif self._ui_check is None:
                add(
                    CheckResult(
                        id="ui.render",
                        stage="ui",
                        status=CheckStatus.SKIPPED,
                        summary="no UI render check is configured on this Mac",
                    )
                )
            else:
                preview = make_preview("ui")
                try:
                    install(preview)
                    ui_checks, ui_env = self._ui_check.run(
                        preview,
                        plan.ui,
                        attempt_dir / "evidence" / "ui",
                        "evidence/ui",
                        stop=stop,
                    )
                finally:
                    preview.close()
                for result in ui_checks:
                    add(result)
                environment |= {f"ui_{k}": v for k, v in ui_env.items()}
        else:
            reached = "ui"

        # 7. candidate-authored tests: supplementary
        supplementary: list[CheckResult] = []
        tests = self._binder.run_candidate_tests(sealed.path, deps.runtime)
        if tests.get("present"):
            supplementary.append(
                CheckResult(
                    id="candidate_tests",
                    stage="tests",
                    required=False,
                    status=CheckStatus.PASSED if tests.get("ok") else CheckStatus.FAILED,
                    summary=f"{tests.get('ran', 0)} candidate test(s); "
                    + ("all passed" if tests.get("ok") else "some failed")
                    + " (supplementary, not acceptance evidence)",
                    detail=tests,
                )
            )
        return finish(supplementary)

    @staticmethod
    def _has_ui(sealed: SealedPackage | None, package_dir: Path) -> bool:
        if sealed is not None:
            return sealed.source.ui is not None and sealed.source.ui.entry is not None
        return (package_dir / "ui").is_dir()
