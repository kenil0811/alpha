"""F05 contract shapes: App source, records/queries, profiles and worker calls."""

from __future__ import annotations

from typing import Any

import pytest
from alpha_contracts.apps import AppSource
from alpha_contracts.broker import CapabilityCall
from alpha_contracts.profiles import (
    DependencyProfile,
    canonical_json,
    manifest_digest,
    seal_profile,
    verify_profile,
)
from alpha_contracts.records import (
    AllOf,
    Clause,
    CollectionSchema,
    FieldSpec,
    Filter,
    Not,
    Record,
    RecordQuery,
)
from pydantic import TypeAdapter, ValidationError


def source(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "contract_version": "0.2",
        "app_id": "demo-app",
        "name": "Demo",
        "description": "A demo",
        "runtime_profile": "pyprof-0123456789abcdef0123",
        "sdk_version": "0.1.0",
        "capabilities": ["records"],
        "collections": [
            {"name": "things", "fields": [{"name": "title", "kind": "text", "required": True}]}
        ],
        "actions": [
            {
                "id": "add",
                "title": "Add",
                "description": "Add a thing",
                "handler": "demo.handlers:add",
                "invocable_from": ["manual"],
                "input_schema": {
                    "type": "object",
                    "properties": {"title": {}},
                    "required": ["title"],
                },
                "output_schema": {"type": "object", "properties": {}},
            }
        ],
    }
    base.update(overrides)
    return base


def test_app_source_accepts_a_minimal_app() -> None:
    parsed = AppSource.model_validate(source())
    assert parsed.action("add") is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"grants": ["records.write"]},  # source cannot assign authority
        {"secrets": {"key": "x"}},
        {"capabilities": ["records", "shell"]},  # unknown capability family
        {"capabilities": []},  # collections need records
        {"app_id": "Bad App"},
        {"contract_version": "0.3"},
        {
            "collections": [
                {
                    "name": "things",
                    "fields": [{"name": "owner", "kind": "reference", "collection": "people"}],
                }
            ]
        },
    ],
)
def test_app_source_rejects_authority_and_inconsistency(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AppSource.model_validate(source(**overrides))


def test_action_schema_must_declare_required_properties() -> None:
    bad = source()
    bad["actions"][0]["input_schema"] = {"type": "object", "properties": {}, "required": ["x"]}
    with pytest.raises(ValidationError):
        AppSource.model_validate(bad)


@pytest.mark.parametrize(
    "field",
    [
        {"name": "id", "kind": "text"},  # reserved
        {"name": "Title", "kind": "text"},  # not an identifier
        {"name": "n", "kind": "text", "minimum": 1},
        {"name": "c", "kind": "choice"},
        {"name": "c", "kind": "choice", "choices": ["a", "a"]},
        {"name": "r", "kind": "reference"},
        {"name": "n", "kind": "number", "minimum": 5, "maximum": 1},
    ],
)
def test_field_specs_are_consistent(field: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        FieldSpec.model_validate(field)


def test_collection_rejects_json_indexes_and_unknown_index_fields() -> None:
    fields = [{"name": "blob", "kind": "json"}, {"name": "title", "kind": "text"}]
    with pytest.raises(ValidationError):
        CollectionSchema.model_validate({"name": "c", "fields": fields, "indexes": [["blob"]]})
    with pytest.raises(ValidationError):
        CollectionSchema.model_validate({"name": "c", "fields": fields, "unique": [["missing"]]})


def test_filter_union_parses_nested_shapes_and_rejects_strings() -> None:
    adapter = TypeAdapter[Filter](Filter)
    parsed = adapter.validate_python(
        {
            "all": [
                {"field": "a", "op": "eq", "value": 1},
                {"not": {"field": "b", "op": "is_null", "value": True}},
            ]
        }
    )
    assert isinstance(parsed, AllOf)
    assert isinstance(parsed.all[0], Clause) and isinstance(parsed.all[1], Not)
    with pytest.raises(ValidationError):
        RecordQuery.model_validate({"collection": "c", "where": "1=1"})
    with pytest.raises(ValidationError):
        RecordQuery.model_validate({"collection": "c", "owner": "other-app"})


def test_record_schema_title_does_not_shadow_typescript_record() -> None:
    assert Record.model_json_schema()["title"] == "AppRecord"


def _profile_content() -> dict[str, Any]:
    return {
        "kind": "python_runtime",
        "role": "app_task_compute",
        "target": {"os": "macos", "arch": "arm64", "python_version": "3.13.9"},
        "locks": [{"path": "requirements.lock", "sha256": "a" * 64}],
        "packages": [
            {"name": "b-pkg", "version": "1", "artifact_sha256": "b" * 64},
            {"name": "a-pkg", "version": "1", "artifact_sha256": "c" * 64},
        ],
        "compatibility": {"contract_version": "0.2", "sdk_version": "0.1.0"},
    }


def test_profile_identity_is_derived_and_verifiable() -> None:
    first = seal_profile(_profile_content())
    second = seal_profile(_profile_content())
    assert first.profile_id == second.profile_id and first.manifest_sha256 == second.manifest_sha256
    assert verify_profile(first) == []
    # Package order does not change identity; any content change does.
    reordered = _profile_content()
    reordered["packages"].reverse()
    assert seal_profile(reordered).profile_id == first.profile_id
    changed = _profile_content()
    changed["packages"][0]["version"] = "2"
    assert seal_profile(changed).profile_id != first.profile_id
    tampered = DependencyProfile.model_validate(
        {**first.model_dump(mode="json"), "target": {"os": "macos", "arch": "x86_64"}}
    )
    assert verify_profile(tampered)


def test_canonical_json_is_sorted_compact_and_rejects_nan() -> None:
    assert canonical_json({"b": 1, "a": [2, {"d": 1, "c": 0}]}) == b'{"a":[2,{"c":0,"d":1}],"b":1}'
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})
    assert manifest_digest({"a": 1, "manifest_sha256": "x"}) == manifest_digest({"a": 1})


def test_capability_calls_are_closed() -> None:
    call = {
        "kind": "call",
        "call_id": "c1",
        "token": "t" * 43,
        "operation": "records.get",
        "args": {},
    }
    CapabilityCall.model_validate(call)
    with pytest.raises(ValidationError):
        CapabilityCall.model_validate({**call, "owner": {"kind": "app", "app_id": "x"}})
    with pytest.raises(ValidationError):
        CapabilityCall.model_validate({**call, "version": 2})


def test_primary_action_names_a_manual_action() -> None:
    """M1 review finding F03: the one action a person runs must exist and be runnable by hand."""
    base = source()
    action_id = base["actions"][0]["id"]
    assert (
        AppSource.model_validate({**base, "primary_action": action_id}).primary_action == action_id
    )
    with pytest.raises(ValidationError, match="not declared"):
        AppSource.model_validate({**base, "primary_action": "missing"})
    helper = {**base["actions"][0], "invocable_from": ["assistant"]}
    with pytest.raises(ValidationError, match="manual"):
        AppSource.model_validate({**base, "actions": [helper], "primary_action": action_id})
