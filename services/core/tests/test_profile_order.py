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
