"""Export JSON Schema for every published contract model.

Usage: python -m alpha_contracts.export [--check]
Writes packages/contracts/schema/<name>.schema.json. --check fails on drift instead of writing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel

from alpha_contracts import CONTRACT_VERSION
from alpha_contracts.apps import AppSource, PackageIndex
from alpha_contracts.artifacts import Artifact
from alpha_contracts.briefs import SolutionBrief
from alpha_contracts.broker import CapabilityCall, CapabilityReply, ModelEstimate
from alpha_contracts.builds import BuildEvent, BuildRequest, BuildResult
from alpha_contracts.profiles import DependencyManifest, DependencyProfile
from alpha_contracts.records import (
    AggregateQuery,
    AggregateResult,
    CollectionSchema,
    Record,
    RecordPage,
    RecordQuery,
)
from alpha_contracts.runs import Run, RunEvent
from alpha_contracts.verification import ValidationPlan, VerificationReport

PUBLISHED: dict[str, type[BaseModel]] = {
    "run": Run,
    "run_event": RunEvent,
    "build_request": BuildRequest,
    "build_result": BuildResult,
    "build_event": BuildEvent,
    "solution_brief": SolutionBrief,
    "app_source": AppSource,
    "package_index": PackageIndex,
    "collection_schema": CollectionSchema,
    "record": Record,
    "record_page": RecordPage,
    "record_query": RecordQuery,
    "aggregate_query": AggregateQuery,
    "aggregate_result": AggregateResult,
    "artifact": Artifact,
    "dependency_profile": DependencyProfile,
    "dependency_manifest": DependencyManifest,
    "capability_call": CapabilityCall,
    "capability_reply": CapabilityReply,
    "model_estimate": ModelEstimate,
    "validation_plan": ValidationPlan,
    "verification_report": VerificationReport,
}

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"


def _strip_property_titles(node: object) -> None:
    """Pydantic titles every property ("Run Id"); they add nothing and make generated
    TypeScript emit an alias per property. Model titles ($defs and root) are kept."""
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            for prop in props.values():
                if isinstance(prop, dict):
                    prop.pop("title", None)
        for value in node.values():
            _strip_property_titles(value)
    elif isinstance(node, list):
        for item in node:
            _strip_property_titles(item)


def render(model: type[BaseModel]) -> str:
    schema = model.model_json_schema()
    _strip_property_titles(schema)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["x-alpha-contract-version"] = CONTRACT_VERSION
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    check = "--check" in args
    drift: list[str] = []
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for name, model in PUBLISHED.items():
        target = SCHEMA_DIR / f"{name}.schema.json"
        rendered = render(model)
        if check:
            if not target.exists() or target.read_text(encoding="utf-8") != rendered:
                drift.append(target.name)
        else:
            target.write_text(rendered, encoding="utf-8")
    if check and drift:
        print(f"contract schema drift: {', '.join(drift)} (run: just contracts)", file=sys.stderr)
        return 1
    if check:
        print(f"contract schemas up to date ({len(PUBLISHED)} files)")
    else:
        print(f"wrote {len(PUBLISHED)} contract schemas to {SCHEMA_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
