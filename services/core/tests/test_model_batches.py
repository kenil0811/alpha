"""Batch model work: one structured call may return a bounded list (a `json` field), so a module
scores or extracts twenty items in one call instead of twenty slow ones."""

from __future__ import annotations

from pathlib import Path

import pytest
from alpha.capabilities.errors import OperationFailed
from alpha.data.values import fields_to_json_schema
from alpha.models.gateway import ModelGateway
from alpha.models.runtime import AppModelService
from alpha.models.structured import StructuredInference
from alpha.storage.control_store import ControlStore
from alpha_contracts.broker import StructuredModelCall
from alpha_contracts.records import FieldSpec


def service(tmp_path: Path) -> AppModelService:
    control = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(control, frozenset({"fake"}))
    return AppModelService(control, gateway, StructuredInference(gateway), "fake")


def test_a_json_field_becomes_a_list_or_object_in_the_schema() -> None:
    schema = fields_to_json_schema([FieldSpec(name="scores", kind="json", required=True)])
    assert schema["properties"]["scores"] == {"type": ["array", "object"]}
    assert schema["required"] == ["scores"]


def test_a_batch_call_returns_a_list_through_the_fake_route(tmp_path: Path) -> None:
    models = service(tmp_path)
    estimate = models.call(
        "run_1",
        "app:demo",
        StructuredModelCall(
            instruction="Score every opening; return under scores a list of {ref, match_level}.",
            input={"openings": [{"ref": 1, "title": "Senior backend"}]},
            fields=[FieldSpec(name="scores", kind="json", required=True)],
        ),
    )
    scores = estimate.output["scores"]
    assert isinstance(scores, list) and scores[0]["ref"] == 1


def test_a_batch_input_may_be_larger_than_a_single_estimate(tmp_path: Path) -> None:
    models = service(tmp_path)
    big = [{"ref": i, "description": "x" * 2000} for i in range(25)]  # ~50 KB
    estimate = models.call(
        "run_2",
        "app:demo",
        StructuredModelCall(
            instruction="Extract facts.",
            input={"postings": big},
            fields=[FieldSpec(name="listings", kind="json", required=True)],
        ),
    )
    assert isinstance(estimate.output["listings"], list)
    huge = [{"ref": i, "description": "x" * 3000} for i in range(25)]  # ~76 KB
    with pytest.raises(OperationFailed) as failed:
        models.call(
            "run_3",
            "app:demo",
            StructuredModelCall(
                instruction="Extract facts.",
                input={"postings": huge},
                fields=[FieldSpec(name="listings", kind="json", required=True)],
            ),
        )
    assert failed.value.code == "limit_exceeded"
