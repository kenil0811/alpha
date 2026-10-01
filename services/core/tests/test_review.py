"""The weekly look across modules suggests and never changes anything."""

from __future__ import annotations

from pathlib import Path

from alpha.context.review import ReviewService
from alpha.models.gateway import ModelGateway
from alpha.models.structured import StructuredInference
from alpha.storage.control_store import ControlStore


def service(tmp_path: Path, pack: str) -> ReviewService:
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(store, frozenset({"fake"}))
    return ReviewService(
        store, gateway, StructuredInference(gateway), default_route="fake", context=lambda _t: pack
    )


def test_a_review_writes_nudges_and_a_dismissal_sticks(tmp_path: Path) -> None:
    svc = service(
        tmp_path,
        "ABOUT THE PERSON:\n- nothing\n\nTHEIR PROJECTS:\n"
        "- Notes [notes]: A list. Keeps: notes (0).",
    )
    assert svc.due() is True
    nudges = svc.run()
    assert [n["next_step"] for n in nudges] == ["Add my first three notes"]
    assert svc.due() is False
    svc.dismiss(nudges[0]["nudge_id"])
    assert svc.nudges() == []
    again = svc.run()
    assert len(again) == 1, "a new look replaces the old nudges"


def test_nothing_to_review_without_modules(tmp_path: Path) -> None:
    svc = service(tmp_path, "ABOUT THE PERSON:\n- nothing recorded yet")
    assert svc.run() == [] and svc.due() is False
