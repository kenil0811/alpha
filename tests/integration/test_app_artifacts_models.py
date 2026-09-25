"""F05.C03: artifacts have correct bytes/digests/provenance, and bounded model results are
correctable estimates rather than facts.

The model route here is the deterministic `fake` control route: it proves the gateway, budget,
validation, provenance and correction mechanics. A live-route smoke run is recorded separately
in the evidence and is not required by this integration check."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from tests.integration.app_harness import act, output, record_evidence, start_app_core
from tests.integration.conftest import AppCore

pytestmark = pytest.mark.integration

ITEMS = "items-fixture"


def test_artifact_bytes_digest_and_provenance(app_core: AppCore, data_dir: Path) -> None:
    core = app_core.core
    for title, quantity in (("apples", 3), ("paper, A4", 10), ('say "hi"', 1)):
        output(core, ITEMS, "add_item", {"title": title, "category": "home", "quantity": quantity})
    run = act(core, ITEMS, "make_report", {})
    report = run["output"]
    expected = 'title,category,quantity\napples,home,3\n"paper, A4",home,10\n"say ""hi""",home,1\n'
    expected_sha = hashlib.sha256(expected.encode()).hexdigest()
    assert report["local_sha256"] == expected_sha == report["sha256"]
    assert report["size_bytes"] == len(expected.encode()) and report["rows"] == 3

    with core.client() as client:
        meta = client.get(f"/api/artifacts/{report['artifact_id']}").json()
        content = client.get(f"/api/artifacts/{report['artifact_id']}/content")
    assert content.content == expected.encode()
    assert content.headers["x-content-sha256"] == expected_sha
    assert content.headers["content-type"].startswith("text/csv")
    assert meta["owner"] == {"kind": "app", "id": ITEMS}
    assert meta["storage_ref"] == f"blob:sha256:{expected_sha}"
    install = app_core.installs["items"]
    assert meta["provenance"] == {
        "created_by": "app_run",
        "run_id": run["run_id"],
        "action_id": "make_report",
        "version_id": install["version_id"],
        "package_sha256": install["package_sha256"],
        "derived_from": [],
        "model_call_ids": [],
    }
    record_evidence(
        "F05.C03-artifact", {"run_id": run["run_id"], "report": report, "metadata": meta}
    )
    # No filesystem path leaves Core.
    assert str(data_dir) not in json.dumps(meta)

    # Reading back through the worker returns identical bytes.
    back = output(core, ITEMS, "read_report", {"artifact_id": report["artifact_id"]})
    assert back == {"text": expected, "sha256": expected_sha}

    # The stored blob is content-addressed, read-only and holds exactly those bytes.
    blob = data_dir / "artifacts" / "blobs" / "sha256" / expected_sha[:2] / expected_sha
    assert blob.read_bytes() == expected.encode()
    assert not blob.stat().st_mode & 0o222


def test_artifact_limits_and_restart_reconciliation(app_core: AppCore, data_dir: Path) -> None:
    core = app_core.core
    assert (
        output(core, ITEMS, "expect_failure", {"case": "artifact_bad_type"})["error_code"]
        == "invalid_input"
    )
    assert (
        output(core, ITEMS, "expect_failure", {"case": "artifact_too_large"})["error_code"]
        == "limit_exceeded"
    )
    report = output(core, ITEMS, "make_report", {})
    core.stop()
    # Simulate a crash mid-stage and a blob written without registration.
    (data_dir / "artifacts" / "staging" / "abandoned.part").write_bytes(b"half")
    orphan = hashlib.sha256(b"orphan").hexdigest()
    orphan_path = data_dir / "artifacts" / "blobs" / "sha256" / orphan[:2] / orphan
    orphan_path.parent.mkdir(parents=True, exist_ok=True)
    orphan_path.write_bytes(b"orphan")
    restarted = start_app_core(data_dir, app_core.profile, app_core.fixtures)
    try:
        assert not (data_dir / "artifacts" / "staging" / "abandoned.part").exists()
        assert not orphan_path.exists()
        back = output(restarted, ITEMS, "read_report", {"artifact_id": report["artifact_id"]})
        assert back["sha256"] == report["sha256"]
    finally:
        restarted.stop()


def test_model_results_are_labelled_estimates_and_correctable(app_core: AppCore) -> None:
    core = app_core.core
    run = act(core, ITEMS, "estimate_quantity", {"title": "batteries"})
    estimate = run["output"]
    # The fake route returns the midpoint of the declared 0..100 bound.
    assert estimate["quantity"] == 50 and estimate["is_estimate"] is True
    assert estimate["route"] == "fake"

    record = output(core, ITEMS, "get_item", {"id": estimate["id"]})["record"]
    provenance = record["provenance"]["quantity"]
    assert provenance["source"] == "model_estimate"
    assert provenance["call_id"] == estimate["call_id"] and provenance["route"] == "fake"
    assert "title" not in record["provenance"]  # typed values carry no model provenance

    with core.client() as client:
        calls = client.get(f"/api/runs/{run['run_id']}/model-calls").json()["model_calls"]
    assert [(c["call_id"], c["status"], c["route_id"]) for c in calls] == [
        (estimate["call_id"], "ok", "fake")
    ]
    assert json.loads(calls[0]["output_json"]) == {"quantity": 50}
    with sqlite3.connect(core.data_dir / "control.sqlite") as conn:
        usage = conn.execute(
            "SELECT route_id, scope_kind FROM model_usage WHERE scope_ref = ?", (run["run_id"],)
        ).fetchall()
    assert usage == [("fake", "app_run")]

    # A person corrects it (UI-started run): the value is theirs now and the estimate is kept
    # as the previous value, not erased.
    corrected = output(
        core,
        ITEMS,
        "correct_quantity",
        {"id": estimate["id"], "expected_revision": estimate["revision"], "quantity": 12},
        origin="ui",
    )
    assert corrected["is_estimate"] is False
    after = corrected["provenance"]["quantity"]
    assert after["source"] == "user_correction"
    assert after["previous"] == {
        "value": 50,
        "source": "model_estimate",
        "call_id": estimate["call_id"],
    }
    record = output(core, ITEMS, "get_item", {"id": estimate["id"]})["record"]
    assert record["values"]["quantity"] == 12 and record["revision"] == estimate["revision"] + 1
    record_evidence(
        "F05.C03-estimate",
        {"estimate": estimate, "model_calls": calls, "usage": usage, "corrected_record": record},
    )

    # An automated run cannot claim to be the person.
    item = output(core, ITEMS, "add_item", {"title": "cups", "category": "home", "quantity": 4})
    failed = act(
        core,
        ITEMS,
        "correct_quantity",
        {"id": item["id"], "expected_revision": item["revision"], "quantity": 1},
        origin="trigger",
        expect="failed",
    )
    assert failed["terminal_reason"] == "operation_failed"
    worker_error = next(e for e in core.events(failed["run_id"]) if e["kind"] == "worker.error")
    assert worker_error["payload"]["operation_code"] == "forbidden"


def test_model_calls_are_bounded(app_core: AppCore) -> None:
    core = app_core.core
    other = output(core, ITEMS, "estimate_quantity", {"title": "tea"})
    borrowed = output(
        core, ITEMS, "expect_failure", {"case": "borrowed_estimate", "arg": other["call_id"]}
    )
    assert borrowed["error_code"] == "forbidden"
    out_of_bounds = output(core, ITEMS, "expect_failure", {"case": "model_out_of_bounds"})
    assert out_of_bounds["error_code"] == "unavailable"
    assert "outside the requested bounds" in out_of_bounds["message"]
    budget = output(core, ITEMS, "expect_failure", {"case": "model_budget"})
    assert budget["error_code"] == "limit_exceeded"
    with sqlite3.connect(core.data_dir / "control.sqlite") as conn:
        statuses = [
            r[0] for r in conn.execute("SELECT status FROM model_calls ORDER BY created_at")
        ]
    assert "rejected" in statuses
