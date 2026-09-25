from datetime import UTC, datetime

import pytest
from alpha_contracts.briefs import Assumption, Delivery, OpenQuestion, SolutionBrief
from pydantic import ValidationError

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def _brief(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "brief_1",
        "revision": 1,
        "conversation_id": "conv_1",
        "created_at": NOW,
        "goal": "Track what I eat",
        "success_summary": "Fast entry, correct totals",
        "delivery": "app",
        "surfaces": ["custom_ui"],
        "inputs": [],
        "primary_journey": [{"action": "Type a food", "expected_result": "An entry appears"}],
        "data_needs": [],
        "actions": [],
        "recurrence": None,
        "constraints": [],
        "acceptance_examples": [],
        "assumptions": [{"text": "Single user", "source": "model_default"}],
        "open_questions": [],
        "unavailable_capabilities": ["records"],
        "selected_context_snapshot_id": "conv_1.context.r1",
    }
    base.update(overrides)
    return base


def test_brief_round_trip_and_delivery_enum() -> None:
    brief = SolutionBrief.model_validate(_brief())
    assert brief.delivery is Delivery.APP
    assert brief.assumptions[0].source == "model_default"
    assert SolutionBrief.model_validate_json(brief.model_dump_json()) == brief


def test_brief_rejects_authority_bearing_or_unknown_fields() -> None:
    for field in ("grant_ids", "credentials", "connection_secret", "release_id"):
        with pytest.raises(ValidationError):
            SolutionBrief.model_validate(_brief(**{field: "x"}))


def test_all_listed_fields_are_required() -> None:
    for missing in (
        "goal",
        "surfaces",
        "assumptions",
        "open_questions",
        "unavailable_capabilities",
    ):
        data = _brief()
        del data[missing]
        with pytest.raises(ValidationError):
            SolutionBrief.model_validate(data)


def test_invalid_enums_and_bad_digest_rejected() -> None:
    with pytest.raises(ValidationError):
        SolutionBrief.model_validate(_brief(delivery="dashboard"))
    with pytest.raises(ValidationError):
        SolutionBrief.model_validate(_brief(surfaces=["popup"]))
    with pytest.raises(ValidationError):
        SolutionBrief.model_validate(
            _brief(inputs=[{"ref": "x", "purpose": "p", "source": "s", "digest": "nope"}])
        )


def test_assumption_and_question_shapes() -> None:
    with pytest.raises(ValidationError):
        Assumption(text="", source="model_default")
    with pytest.raises(ValidationError):
        Assumption(text="ok", source="guess")
    q = OpenQuestion(id="q1", question="How much?", options=["a", "b"], why_it_matters="It matters")
    assert q.options == ["a", "b"]
