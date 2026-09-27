"""Settings the person changes: model per stage and build limits, applied without a restart."""

from __future__ import annotations

from pathlib import Path

import pytest
from alpha.models.gateway import ModelGateway
from alpha.models.preferences import FIELDS, InvalidSetting, Preferences
from alpha.storage.control_store import ControlStore


def test_defaults_are_described_and_changes_persist(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    prefs = Preferences(store)
    described = prefs.describe()
    assert [d["id"] for d in described] == [f.id for f in FIELDS]
    assistant = next(d for d in described if d["id"] == "models.assistant")
    assert assistant["value"] == "sonnet" and assistant["group"] == "Models"
    builder = next(d for d in described if d["id"] == "models.builder_new")
    assert builder["value"] == "default", "building keeps the strongest model by default"
    assert [o["value"] for o in assistant["options"]] == ["default", "opus", "sonnet", "haiku"]

    prefs.update({"models.builder_new": "sonnet", "build.max_turns": "120"})
    again = Preferences(ControlStore(tmp_path / "control.sqlite"))
    assert again.get("models.builder_new") == "sonnet"
    assert again.get("build.max_turns") == 120


@pytest.mark.parametrize(
    ("values", "problem"),
    [
        ({"models.assistant": "gpt"}, "not one of the choices"),
        ({"build.max_turns": 5}, "at least 20"),
        ({"build.max_total_minutes": 999}, "at most 120"),
        ({"nope": 1}, "no setting"),
        ({"build.max_repair_attempts": "two"}, "whole number"),
    ],
)
def test_bad_values_are_refused_with_the_reason(tmp_path: Path, values: dict, problem: str) -> None:
    prefs = Preferences(ControlStore(tmp_path / "control.sqlite"))
    with pytest.raises(InvalidSetting, match=problem):
        prefs.update(values)
    assert prefs.values() == {f.id: f.default for f in FIELDS}, "nothing changed"


def test_the_gateway_applies_the_chosen_model_per_stage_and_the_limits(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    prefs = Preferences(store)
    gateway = ModelGateway(
        store,
        frozenset({"fake", "claude-code-cli"}),
        max_attempt_seconds=1,
        max_total_seconds=1,
        preferences=prefs,
    )
    assert gateway.route("claude-code-cli", stage="assistant").model == "sonnet"
    assert gateway.route("claude-code-cli", stage="builder_new").model == "default"
    prefs.update({"models.assistant": "haiku", "models.builder_change": "sonnet"})
    assert gateway.route("claude-code-cli", stage="assistant").model == "haiku"
    assert gateway.route("claude-code-cli", stage="builder_change").model == "sonnet"
    assert gateway.route("claude-code-cli", stage="builder_new").model == "default"
    assert gateway.route("claude-code-cli").model == "default", "no stage, no override"
    assert gateway.route("fake", stage="assistant").model == "none", "the fake route has no model"

    prefs.update(
        {"build.max_attempt_minutes": 5, "build.max_total_minutes": 12, "build.max_turns": 30}
    )
    budget = gateway.budget(gateway.route("claude-code-cli"))
    assert (budget.max_attempt_seconds, budget.max_total_seconds, budget.max_turns) == (
        300,
        720,
        30,
    )
