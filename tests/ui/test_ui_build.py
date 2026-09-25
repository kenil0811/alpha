"""F06.C04: two neutral UI compositions (and the App template) build and run from the same pinned
kit/bridge packages installed in the managed UI build profile; no vendored forks, no remote runtime
imports, no App-specific Node server. Real tools: pnpm pack/install, Vite from the profile, Core."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.integration.conftest import REPO_ROOT, start_core

pytestmark = pytest.mark.integration

COMPOSITIONS = REPO_ROOT / "tests" / "ui" / "compositions"
TEMPLATE_UI = REPO_ROOT / "templates" / "app" / "ui" / "src"
BUILD_TOOL = REPO_ROOT / "tools" / "ui_build" / "build_app_ui.mjs"
KIT_SRC = REPO_ROOT / "packages" / "ui-kit" / "src"


def node() -> str:
    keg = Path("/opt/homebrew/opt/node@24/bin/node")
    return str(keg) if keg.exists() else "node"


def publish_ui_profile(root: Path) -> dict[str, Any]:
    env = {**os.environ, "PATH": f"{Path(node()).parent}:{os.environ.get('PATH', '')}"}
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "build_ui_profile.py"), "--root", str(root)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    data: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    return data


def build(profile: Path, source: Path, out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            node(),
            str(BUILD_TOOL),
            "--profile",
            str(profile),
            "--src",
            str(source),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )


def unseal(root: Path) -> None:
    """Sealed profiles are read-only; make them removable once the tests are done."""
    for path in [root, *root.rglob("*")]:
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | stat.S_IWUSR)


@pytest.fixture(scope="module")
def ui_profile(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    root = tmp_path_factory.mktemp("ui-profiles")
    first = publish_ui_profile(root)
    again = publish_ui_profile(root)
    assert first["published"] is True and again["published"] is False
    assert again["profile_id"] == first["profile_id"]
    first["root"] = str(root)
    yield first
    unseal(root)


def test_compositions_and_template_share_one_pinned_kit(
    ui_profile: dict[str, Any], tmp_path: Path
) -> None:
    profile = Path(ui_profile["path"])
    manifest = json.loads((profile / "manifest.json").read_text())
    pins = {p["name"]: p for p in manifest["packages"]}
    reports = {}
    for name, source in (
        ("review", COMPOSITIONS / "review"),
        ("entry", COMPOSITIONS / "entry"),
        ("template", TEMPLATE_UI),
    ):
        result = build(profile, source, tmp_path / name)
        assert result.returncode == 0, result.stderr[-3000:]
        reports[name] = json.loads((tmp_path / name / "build.json").read_text())

    for name, report in reports.items():
        assert report["profile"] == {
            "profile_id": ui_profile["profile_id"],
            "manifest_sha256": ui_profile["manifest_sha256"],
        }
        # The exact packed kit and bridge from the profile, not the workspace sources.
        assert (
            report["kit"]["artifact"]
            == pins["@alpha/ui-kit"]["artifact"]
            == "alpha-ui-kit-0.1.0.tgz"
        )
        assert report["kit"]["installed_tree_sha256"] == pins["@alpha/ui-kit"]["artifact_sha256"]
        assert (
            report["bridge"]["installed_tree_sha256"] == pins["@alpha/ui-bridge"]["artifact_sha256"]
        )
        packages = report["modules"]["packages"]
        assert "@alpha/ui-kit@0.1.0" in packages and "@alpha/ui-bridge@0.2.0" in packages
        assert report["modules"]["unpinned"] == []
        # App modules are only the composition's own files (plus the platform-written index.html).
        assert set(report["modules"]["app"]) <= {"index.html", *report["source"]["files"]}, name
    assert reports["review"]["kit"] == reports["entry"]["kit"] == reports["template"]["kit"]


def test_compositions_do_not_vendor_kit_code() -> None:
    kit_signatures = {
        "export function QuickEntry",
        "export function RecordTable",
        "export function ReviewQueue",
        "export function TrendChart",
        "class BridgeClient",
        ".a-quick-entry",
    }
    for source in [*COMPOSITIONS.rglob("*"), *TEMPLATE_UI.rglob("*")]:
        if source.is_file():
            text = source.read_text()
            assert not any(sig in text for sig in kit_signatures), source
            imports = re.findall(r'from\s+"([^"]+)"|import\s+"([^"]+)"', text)
            for module in [a or b for a, b in imports]:
                assert module in {
                    "react",
                    "react-dom/client",
                    "@alpha/ui-kit",
                    "@alpha/ui-kit/styles.css",
                }, (source, module)


def test_output_is_one_static_document_with_a_closed_csp(
    ui_profile: dict[str, Any], tmp_path: Path
) -> None:
    profile = Path(ui_profile["path"])
    first, second = tmp_path / "a", tmp_path / "b"
    assert build(profile, COMPOSITIONS / "entry", first).returncode == 0
    assert build(profile, COMPOSITIONS / "entry", second).returncode == 0
    html = (first / "index.html").read_text()
    assert html == (second / "index.html").read_text(), "builds are not deterministic"
    assert sorted(p.name for p in first.iterdir()) == ["build.json", "index.csp", "index.html"]
    csp = (first / "index.csp").read_text()
    for directive in (
        "default-src 'none'",
        "connect-src 'none'",
        "form-action 'none'",
        "base-uri 'none'",
        "font-src 'none'",
    ):
        assert directive in csp
    assert re.search(r"script-src 'sha256-[A-Za-z0-9+/=]+'$", csp.split(";")[1].strip())
    assert len(re.findall(r"<script\b[^>]*\bsrc=", html)) == 0
    assert html.count("</script>") == 1
    assert not re.search(r"""\bimport\s*\(\s*["'`](?:https?:)?//""", html)


@pytest.mark.parametrize(
    ("main", "expected"),
    [
        ('import x from "https://example.com/x.js";\nconsole.log(x);\n', "remote"),
        (
            f'import {{ QuickEntry }} from "{KIT_SRC}/index.ts";\nconsole.log(QuickEntry);\n',
            "outside the App source and the profile",
        ),
    ],
    ids=["remote-import", "workspace-kit-source"],
)
def test_builds_refuse_remote_and_unpinned_sources(
    ui_profile: dict[str, Any], tmp_path: Path, main: str, expected: str
) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "main.tsx").write_text(main)
    result = build(Path(ui_profile["path"]), source, tmp_path / "out")
    assert result.returncode != 0
    assert expected in (result.stderr + result.stdout)


def test_core_registers_the_ui_profile_and_quarantines_a_changed_one(
    ui_profile: dict[str, Any], tmp_path: Path
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    core = start_core(data, extra_env={"ALPHA_PROFILES_DIR": ui_profile["root"]})
    try:
        with core.client() as client:
            rows = client.get("/api/runtime-profiles").json()["profiles"]
    finally:
        core.stop()
    row = next(r for r in rows if r["profile_id"] == ui_profile["profile_id"])
    assert row["kind"] == "ui_build" and row["state"] == "ready"

    # A separately published copy with one installed file changed is quarantined.
    copy_root = tmp_path / "copy"
    copy_root.mkdir()
    target = copy_root / ui_profile["profile_id"]
    shutil.copytree(ui_profile["path"], target, symlinks=True)
    victim = target / "node_modules" / "@alpha" / "ui-kit" / "package.json"
    victim = victim.resolve()
    for path in (target, victim.parent, victim):
        path.chmod(path.stat().st_mode | stat.S_IWUSR)
    victim.write_text(victim.read_text() + "\n")
    data2 = tmp_path / "data2"
    data2.mkdir()
    core = start_core(data2, extra_env={"ALPHA_PROFILES_DIR": str(copy_root)})
    try:
        with core.client() as client:
            rows = client.get("/api/runtime-profiles").json()["profiles"]
    finally:
        core.stop()
        for path in target.rglob("*"):
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | stat.S_IWUSR)
    changed = next(r for r in rows if r["profile_id"] == ui_profile["profile_id"])
    assert changed["state"] == "quarantined" and "installed files differ" in changed["reason"]
