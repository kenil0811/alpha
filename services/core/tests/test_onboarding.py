"""The first conversation: five answers become facts, and Alpha proposes a first shape."""

from __future__ import annotations

from pathlib import Path

from alpha.context.onboarding import QUESTIONS, OnboardingService
from alpha.context.profile import ProfileService
from alpha.models.gateway import ModelGateway
from alpha.models.structured import StructuredInference
from alpha.storage.control_store import ControlStore


def test_answers_become_facts_and_a_first_shape_is_proposed(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(store, frozenset({"fake"}))
    profile = ProfileService(store)
    svc = OnboardingService(
        store, profile, gateway, StructuredInference(gateway), default_route="fake"
    )
    status = svc.status()
    assert status["done"] is False and [q["id"] for q in status["questions"]] == [
        q["id"] for q in QUESTIONS
    ]

    after = svc.answer(
        {
            "occupation": "MSc student",
            "goal": "a backend job",
            "tools": "LinkedIn, Notion",
            "nonsense": "x",
        }
    )
    assert after["done"] is True
    assert [o["title"] for o in after["proposal"]["options"]] == ["Coursework", "Job applications"]
    facts = {f.field: f.value for f in profile.current()}
    assert facts == {
        "occupation": "MSc student",
        "current_goal": "a backend job",
        "work_tools": "LinkedIn, Notion",
    }
    assert all(f.provenance == "person" for f in profile.current())


def test_skipping_is_remembered(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(store, frozenset({"fake"}))
    svc = OnboardingService(
        store, ProfileService(store), gateway, StructuredInference(gateway), default_route="fake"
    )
    assert svc.skip()["done"] is True
    assert svc.status()["proposal"]["skipped"] is True
