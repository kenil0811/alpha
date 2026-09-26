"""Helpers for F07 integration tests: real App runtime and UI build profiles, the real UI build
tool and render check with the pinned headless browser, and a Core configured for the whole
build pipeline. Only the builder is a deterministic fake: it copies fixture packages, so the
checks (not the generation) are what these tests prove."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.integration.conftest import REPO_ROOT, CoreProcess, start_core

BUILD_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "builds"
NODE = Path("/opt/homebrew/opt/node@24/bin/node")
TIMEZONE = "Asia/Kolkata"
TERMINAL = {"ready", "failed", "cancelled"}


def node() -> Path:
    return NODE if NODE.exists() else Path(shutil.which("node") or "node")


def validator_browser() -> Path | None:
    """The headless shell Playwright 1.62.0 pins (Chrome for Testing 151.0.7922.34)."""
    browsers = json.loads(
        (REPO_ROOT / "workers/validator/node_modules/playwright-core/browsers.json").read_text()
    )
    revision = next(
        b["revision"] for b in browsers["browsers"] if b["name"] == "chromium-headless-shell"
    )
    cache = Path(
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or Path.home() / "Library/Caches/ms-playwright"
    )
    exe = (
        cache
        / f"chromium_headless_shell-{revision}"
        / "chrome-headless-shell-mac-arm64"
        / "chrome-headless-shell"
    )
    return exe if exe.is_file() else None


def build_ui_profile(root: Path) -> dict[str, Any]:
    env = {**os.environ, "PATH": f"{node().parent}:{os.environ.get('PATH', '')}"}
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "build_ui_profile.py"), "--root", str(root)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"UI profile build failed: {result.stderr[-3000:]}")
    data: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    return data


# ----- fixture packages and their single-defect variants -----------------------------------


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, (path, old)
    path.write_text(text.replace(old, new), encoding="utf-8")


def _handlers(pkg: Path) -> Path:
    return pkg / "src" / "notes_app" / "handlers.py"


def _yaml(pkg: Path) -> Path:
    return pkg / "app.yaml.template"


def _screen(pkg: Path) -> Path:
    return pkg / "ui" / "src" / "main.tsx"


def missing_handler(p: Path) -> None:
    """count_notes names a function that does not exist."""
    _edit(_yaml(p), "notes_app.handlers:count_notes", "notes_app.handlers:count_all")


def fake_persistence(p: Path) -> None:
    """add_note says it saved but never writes a record."""
    _edit(
        _handlers(p),
        '    record = ctx.records.create(\n        "notes", {"title": title.strip(), '
        '"noted_on": ctx.today().isoformat()}\n    )\n    return {"id": record.id, '
        '"revision": record.revision}',
        '    return {"id": "note-1", "revision": 1}',
    )


def broken_action(p: Path) -> None:
    """The primary action writes to a collection that does not exist, so it always fails."""
    _edit(_handlers(p), '"notes", {"title"', '"note", {"title"')


def overflow(p: Path) -> None:
    """The screen has a strip wider than a 768px window."""
    (p / "ui" / "src" / "wide.css").write_text(".wide-strip { width: 1400px; }\n")
    _edit(
        _screen(p),
        'import "@alpha/ui-kit/styles.css";',
        'import "@alpha/ui-kit/styles.css";\nimport "./wide.css";',
    )
    _edit(
        _screen(p),
        '      <Section title="Latest">',
        '      <div className="wide-strip">Summary strip</div>\n      <Section title="Latest">',
    )


def ui_fake_save(p: Path) -> None:
    """The screen keeps entries in local state and never calls the action."""
    _edit(
        _screen(p),
        'import { StrictMode } from "react";',
        'import { StrictMode, useState } from "react";',
    )
    _edit(
        _screen(p),
        '  const add = useAction("add_note");',
        '  const add = useAction("add_note");\n  void add;\n'
        "  const [local, setLocal] = useState<string[]>([]);",
    )
    _edit(
        _screen(p),
        "onSubmit={async (title) => void (await add.run({ title }))}",
        "onSubmit={async (title) => void setLocal((l) => [String(title), ...l])}",
    )
    _edit(
        _screen(p),
        '      <Section title="Latest">',
        '      <Section title="Just added">{local.map((t) => <p key={t}>{t}</p>)}</Section>\n'
        '      <Section title="Latest">',
    )


def ui_hides_errors(p: Path) -> None:
    """The screen swallows failures: a failed read looks empty, a failed save looks saved."""
    _edit(
        _screen(p),
        "onSubmit={async (title) => void (await add.run({ title }))}",
        "onSubmit={async (title) => { try { await add.run({ title }); } catch { /* ignored */ } }}",
    )
    _edit(_screen(p), "          error={recent.error}\n", "")


def undeclared_import(p: Path) -> None:
    """Imports a package the runtime profile does not contain."""
    _edit(
        _handlers(p),
        "from alpha_sdk import Context\n",
        "import requests\nfrom alpha_sdk import Context\n",
    )


def declared_module(p: Path) -> None:
    """Declares an extra module in app.yaml."""
    _edit(
        _yaml(p),
        'sdk_version: "{{SDK_VERSION}}"\n',
        'sdk_version: "{{SDK_VERSION}}"\nmodules: {requests: "2.32.3"}\n',
    )


def core_import(p: Path) -> None:
    """Reaches into Core internals."""
    _edit(
        _handlers(p),
        "from alpha_sdk import Context\n",
        "from alpha.data import store\nfrom alpha_sdk import Context\n",
    )


def installer_import(p: Path) -> None:
    """Tries to install packages at run time with the standard library's bundled installer."""
    _edit(
        _handlers(p),
        "def count_notes(ctx: Context) -> dict[str, Any]:\n",
        "def count_notes(ctx: Context) -> dict[str, Any]:\n"
        "    import ensurepip\n\n    ensurepip.bootstrap()\n",
    )


def requirements_file(p: Path) -> None:
    """Ships its own dependency declaration."""
    (p / "requirements.txt").write_text("requests==2.32.3\n")


def wrong_profile(p: Path) -> None:
    """Names the UI build profile as its Python runtime."""
    _edit(
        _yaml(p),
        'runtime_profile: "{{RUNTIME_PROFILE}}"',
        'runtime_profile: "{{UI_BUILD_PROFILE}}"',
    )


def lookalike_titles(p: Path) -> None:
    """Not a defect: section and card titles reuse the field's words ("Write a note", "Notes
    saved"). The render check must still find the field labelled "Note"."""
    _edit(_screen(p), '<Section title="Add">', '<Section title="Write a note">')
    _edit(_screen(p), '<Section title="Latest">', '<Section title="Latest notes">')
    _edit(
        _screen(p),
        "import { AlphaApp, Page,",
        "import { AlphaApp, MetricCard, Page,",
    )
    _edit(
        _screen(p),
        '      <Section title="Latest notes">',
        '      <MetricCard label="Notes saved" value={recent.records.length} />\n'
        '      <Section title="Latest notes">',
    )


def missing_prop(p: Path) -> None:
    """The table omits its required caption (found live: it crashed the screen at run time)."""
    _edit(_screen(p), '          caption="Latest notes"\n', "")


def entry_only(p: Path) -> None:
    """Not a defect: the screen only adds notes and reads nothing back, so a failed read cannot
    show and must not be demanded."""
    text = _screen(p).read_text()
    start = text.index('      <Section title="Latest">')
    end = text.index("    </Page>")
    text = text[:start] + text[end:]
    text = text.replace('  const recent = useView<Note>("notes.recent", { limit: 20 });\n', "")
    kit_import = text[text.index("import { AlphaApp") : text.index('from "@alpha/ui-kit";')]
    text = text.replace(kit_import, "import { AlphaApp, Page, QuickEntry, Section, useAction } ")
    text = text.replace("type Note = { title: string; noted_on: string };\n\n", "")
    _screen(p).write_text(text)


def notes_slow(p: Path) -> None:
    """Not a defect: adds `slow_note`, which marks its scratch, waits, then saves a note, so a
    run can be cancelled mid-way (F08.C04)."""
    _edit(
        _yaml(p),
        "  - id: count_notes\n",
        "  - id: slow_note\n"
        "    title: Add a note slowly\n"
        "    description: Wait, then save one note.\n"
        "    handler: notes_app.handlers:slow_note\n"
        "    invocable_from: [manual]\n"
        "    effect_class: local_write\n"
        "    capability_requirements: [records]\n"
        "    timeout_seconds: 120\n"
        "    input_schema:\n"
        "      type: object\n"
        "      required: [title, seconds]\n"
        "      properties: {title: {type: string, minLength: 1}, seconds: {type: number}}\n"
        "    output_schema:\n"
        "      type: object\n"
        "      required: [id, revision, scratch, pid]\n"
        "      properties: {id: {type: string}, revision: {type: integer},\n"
        "        scratch: {type: string}, pid: {type: integer}, python: {type: string}}\n"
        "  - id: count_notes\n",
    )
    _edit(
        _handlers(p),
        "def count_notes(",
        "def slow_note(ctx: Context, title: str, seconds: float) -> dict[str, Any]:\n"
        "    import os\n    import sys\n    import time\n\n"
        "    scratch = os.getcwd()\n"
        "    with open(os.path.join(scratch, 'mine.txt'), 'w') as handle:\n"
        "        handle.write(title)\n"
        "    time.sleep(seconds)\n"
        "    record = ctx.records.create(\n"
        "        'notes', {'title': title, 'noted_on': ctx.today().isoformat()}\n"
        "    )\n"
        "    return {\n"
        "        'id': record.id, 'revision': record.revision, 'scratch': scratch,\n"
        "        'pid': os.getpid(), 'python': os.path.realpath(sys.executable),\n"
        "    }\n\n\n"
        "def count_notes(",
    )


VARIANTS: dict[str, Callable[[Path], None]] = {
    f.__name__: f
    for f in (
        missing_handler,
        fake_persistence,
        broken_action,
        overflow,
        ui_fake_save,
        ui_hides_errors,
        undeclared_import,
        declared_module,
        core_import,
        installer_import,
        requirements_file,
        wrong_profile,
        lookalike_titles,
        missing_prop,
        entry_only,
        notes_slow,
    )
}


def render_packages(target: Path) -> Path:
    """notes_ok plus one directory per single-defect variant."""
    target.mkdir(parents=True, exist_ok=True)
    base = BUILD_FIXTURES / "notes_ok"
    shutil.copytree(base, target / "notes_ok", ignore=shutil.ignore_patterns("__pycache__"))
    for name, mutate in VARIANTS.items():
        dest = target / name
        shutil.copytree(base, dest, ignore=shutil.ignore_patterns("__pycache__"))
        mutate(dest)
    return target


NOTES_PLAN: dict[str, Any] = {
    "scenarios": [
        {
            "id": "add_and_count",
            "description": "A saved note is stored with today's date and counted",
            "steps": [
                {
                    "kind": "invoke",
                    "id": "add",
                    "action": "add_note",
                    "input": {"title": "Buy milk"},
                },
                {
                    "kind": "records",
                    "id": "stored",
                    "collection": "notes",
                    "count": 1,
                    "includes": [{"title": "Buy milk", "noted_on": {"$today": 0}}],
                },
                {
                    "kind": "invoke",
                    "id": "count",
                    "action": "count_notes",
                    "input": {},
                    "output": {"count": 1},
                    "exact": True,
                },
            ],
        },
        {
            "id": "blank_refused",
            "description": "A blank note is refused and nothing is stored",
            "steps": [
                {
                    "kind": "invoke",
                    "id": "blank",
                    "action": "add_note",
                    "input": {"title": ""},
                    "expect": "failed",
                },
                {"kind": "records", "id": "nothing", "collection": "notes", "count": 0},
            ],
        },
    ],
    "ui": {
        "primary": [
            {"kind": "fill", "label": "Note", "text": "Buy milk"},
            {"kind": "press", "key": "Enter"},
        ],
        "saved": {
            "kind": "records",
            "id": "saved",
            "collection": "notes",
            "includes": [{"title": "Buy milk"}],
        },
        "shows": ["Buy milk"],
        "seed": [
            {
                "kind": "invoke",
                "id": "long",
                "action": "add_note",
                "input": {
                    "title": "Call the plumber about the kitchen sink leak before Friday "
                    "afternoon, and ask about the yearly boiler service as well"
                },
            }
        ],
        "seed_shows": ["Call the plumber"],
    },
}


# ----- a Core configured for the build pipeline ------------------------------------------


@dataclass
class BuildCore:
    core: CoreProcess
    profiles: Path
    packages: Path


def start_build_core(
    data_dir: Path,
    profiles: Path,
    packages: Path,
    extra_env: dict[str, str] | None = None,
    *,
    token: str | None = None,
) -> CoreProcess:
    browser = validator_browser()
    env = {
        "ALPHA_PROFILES_DIR": str(profiles),
        "ALPHA_PLATFORM_RESOURCES": str(REPO_ROOT),
        "ALPHA_NODE": str(node()),
        "ALPHA_FAKE_BUILDER_PACKAGES": str(packages),
        "ALPHA_TIMEZONE": TIMEZONE,
        "ALPHA_APP_MODEL_ROUTE": "fake",
    }
    if browser is not None:
        env["ALPHA_UI_BROWSER"] = str(browser)
    env.update(extra_env or {})
    return start_core(data_dir, token=token, extra_env=env)


def submit(
    core: CoreProcess, goal: str, plan: dict[str, Any] | None = None, **extra: Any
) -> dict[str, Any]:
    body = {"goal": goal, "validation_plan": plan or NOTES_PLAN, "route_id": "fake", **extra}
    with core.client() as client:
        response = client.post("/api/builds", json=body)
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


def wait_build(core: CoreProcess, build_id: str, timeout: float = 240.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        with core.client() as client:
            last = client.get(f"/api/builds/{build_id}").json()
        if last["state"] in TERMINAL:
            return last
        time.sleep(0.25)
    raise AssertionError(f"build {build_id} stayed {last.get('state')}")


def events(core: CoreProcess, build_id: str) -> list[dict[str, Any]]:
    with core.client() as client:
        found: list[dict[str, Any]] = client.get(f"/api/builds/{build_id}/events").json()["events"]
    return found


def report(core: CoreProcess, build: dict[str, Any], attempt: int = -1) -> dict[str, Any]:
    ref = build["attempts"][attempt]["report_ref"]
    assert ref, build["attempts"][attempt]
    data: dict[str, Any] = json.loads((core.data_dir / "builds" / ref).read_text())
    return data


def checks(rep: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in rep["checks"]}


def failed(rep: dict[str, Any]) -> list[str]:
    return [c["id"] for c in rep["checks"] if c["status"] == "failed"]


def no_local_paths(text: str, *roots: Path) -> list[str]:
    """Absolute device paths that leaked into a portable record."""
    found = [str(r) for r in roots if str(r) in text]
    found += re.findall(r"/Users/[^\"'\s]+", text)
    return found
