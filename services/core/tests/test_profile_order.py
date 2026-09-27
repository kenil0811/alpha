"""Published profiles register oldest build first, so the newest build becomes the default for
new Apps. Found live on 2026-09-27: a stale pre-F07 profile sorted last by id and became the
default, and every build failed its import check."""

from __future__ import annotations

import json
from pathlib import Path

from alpha.execution.profiles import _built_at


def test_profiles_sort_by_build_time_not_by_id(tmp_path: Path) -> None:
    older = tmp_path / "pyprof-zzzz"
    newer = tmp_path / "pyprof-aaaa"
    for target, when in ((older, "2026-09-25T20:27:39Z"), (newer, "2026-09-26T14:49:37Z")):
        target.mkdir()
        (target / "installation.json").write_text(json.dumps({"created_at": when}))
    unreadable = tmp_path / "pyprof-broken"
    unreadable.mkdir()
    ordered = sorted(tmp_path.iterdir(), key=_built_at)
    assert [p.name for p in ordered] == ["pyprof-broken", "pyprof-zzzz", "pyprof-aaaa"]


def test_repointing_a_package_changes_only_its_runtime_profile() -> None:
    from alpha.solutions.registry import repoint_runtime

    text = "app_id: x\nruntime_profile: pyprof-old\nsdk_version: 0.1.0\n"
    assert repoint_runtime(text, "pyprof-new") == (
        "app_id: x\nruntime_profile: pyprof-new\nsdk_version: 0.1.0\n"
    )


def test_the_sdk_source_digest_changes_when_the_sdk_changes(tmp_path: Path) -> None:
    from alpha.execution.profiles import sdk_source_digest

    sdk = tmp_path / "packages" / "app-sdk" / "alpha_sdk"
    sdk.mkdir(parents=True)
    (tmp_path / "packages" / "app-sdk" / "pyproject.toml").write_text("[project]\nname='x'\n")
    (sdk / "web.py").write_text("def get(url): ...\n")
    (sdk / "__pycache__").mkdir()
    (sdk / "__pycache__" / "web.cpython-313.pyc").write_bytes(b"\x00")
    before = sdk_source_digest(tmp_path)
    assert before == sdk_source_digest(tmp_path), "stable across calls"
    (sdk / "__pycache__" / "web.cpython-313.pyc").write_bytes(b"\x01")
    assert sdk_source_digest(tmp_path) == before, "bytecode caches do not count"
    (sdk / "web.py").write_text("def get(url, rendered=False): ...\n")
    assert sdk_source_digest(tmp_path) != before
