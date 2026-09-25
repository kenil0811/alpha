#!/usr/bin/env python3
"""Alpha R2 snapshot/task bookkeeping. Standard library only; never executes tests.

This checks content hashes, task dependencies and evidence references. It cannot
prove that an evidence report is true or that a product/release is qualified.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timezone


def render_packets(registry):
    """One readable rendering of the machine-owned packet definitions."""
    lines = [
        "# Per-ticket execution packets", "",
        "Clean-start R2 · handoff revision 3 · 25 September 2026. Generated from TASKS.json; do not edit independently.", "",
        "The implementation plan owns scope and gates. TASKS.json owns ordered packet steps and required checks. Product and specification owners define behavior. The helper verifies this rendering against the registry.", "",
        "## Rules for every packet", "",
        "Read the common sources in TASKS.json and the packet's references. #N denotes a numbered section; #Fxx denotes a ticket heading, not a guaranteed Markdown anchor. Proposed paths are ownership guidance, not existing files. Create only exercised code; justify directly required shared-contract/test changes.", "",
        "Initially implement F01–F08 only and stop at M1 for product review. Later tickets are fully specified for continuity but require an explicit scope extension under the playbook. Dependency readiness does not override this boundary.", "",
        "Every numbered check is required for completion. Record expected/observed behavior, actual command or observation protocol, result, exact environment and relevant code/package/input identities. Integration uses real components; native requires the supported Mac; live_model/live_source require actual authorized calls; user_study requires people. Review is not a substitute for those checks.", "",
        "F01 creates just verify-ticket F01 and the real dispatcher; unknown/unimplemented recipes fail. Subsequent tickets register meaningful automated checks and separately report native/live/user requirements. Missing access is blocked, never a fabricated pass. Follow AI_Coding_Agent_Playbook.md for evidence, local state and scope. The helper checks bookkeeping, not evidence truth or product quality.", "",
    ]
    for task in registry["tickets"]:
        lines.extend([
            f"## {task['id']} — {task['title']}", "",
            "**Completion prerequisites:** " + (", ".join(task["depends_on"]) or "none") + ".",
            "**Owned areas:** " + "; ".join(task["owned_areas"]) + ".",
            "**Read:** " + "; ".join(task["read"]) + ".", "",
            "**Implement in this order:**", "",
        ])
        lines.extend(f"{i}. {step}" for i, step in enumerate(task["steps"], 1))
        lines.extend(["", "**Required checks:**", "", "| ID | Expected result | Evidence |", "|---|---|---|"])
        for check in task["required_checks"]:
            expected = check["expected"].replace("|", "\\|")
            lines.append(f"| {check['id']} | {expected} | {check['evidence_kind']} |")
        lines.extend(["", "**Scope boundary:** " + task["scope_boundary"], "",
                      f"**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `{task['verification_command']}`. Required pending checks block completion.", ""])
    return "\n".join(lines)


def allowed_tasks(registry, through):
    targets = registry["execution_policy"]["milestone_targets"]
    if through not in targets:
        raise ValueError(f"Unknown scope milestone: {through}")
    tasks = {t["id"]: t for t in registry["tickets"]}
    allowed = set(targets[through])
    pending = list(allowed)
    while pending:
        for dep in tasks[pending.pop()]["depends_on"]:
            if dep not in allowed:
                allowed.add(dep)
                pending.append(dep)
    return allowed


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def within(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if Path(relative).is_absolute() or not candidate.is_relative_to(root.resolve()):
        raise ValueError(f"Path leaves its permitted root: {relative}")
    return candidate


def verify(snapshot: Path):
    manifest_path = snapshot / "MANIFEST.json"
    manifest = read_json(manifest_path)
    if manifest.get("baseline") != "R2":
        raise ValueError("Expected an R2 manifest")
    members = manifest.get("documents", [])
    if not members:
        raise ValueError("Manifest has no documents")
    seen = set()
    for entry in members:
        name = entry["path"]
        if name in seen:
            raise ValueError(f"Duplicate manifest path: {name}")
        seen.add(name)
        path = within(snapshot, name)
        if not path.is_file() or digest(path) != entry["snapshot_sha256"]:
            raise ValueError(f"Missing or changed snapshot file: {name}")
    for name in ("delivery/TASKS.json", "delivery/Task_Packets.md", "delivery/agent_handoff.py"):
        if name not in seen:
            raise ValueError(f"Required handoff file missing from manifest: {name}")
    registry = read_json(snapshot / "delivery/TASKS.json")
    if registry.get("registry_version") != 2:
        raise ValueError("Expected task registry version 2")
    tasks = {t["id"]: t for t in registry["tickets"]}
    if set(tasks) != {f"F{i:02}" for i in range(1, 25)} or len(registry["tickets"]) != 24:
        raise ValueError("Expected exactly one task each for F01 through F24")
    references = list(registry["common_reading"])
    all_checks = set()
    packets = (snapshot / "delivery/Task_Packets.md").read_text(encoding="utf-8")
    if packets != render_packets(registry):
        raise ValueError("Task_Packets.md differs from its TASKS.json rendering")
    for task in tasks.values():
        if not set(task["depends_on"]) <= set(tasks) or task["id"] in task["depends_on"]:
            raise ValueError(f"Invalid dependencies for {task['id']}")
        references.extend(task["read"])
        if not task["steps"] or not task["required_checks"]:
            raise ValueError(f"Incomplete packet: {task['id']}")
        for check in task["required_checks"]:
            cid = check["id"]
            if cid in all_checks or not cid.startswith(task["id"] + ".C") or cid not in packets:
                raise ValueError(f"Invalid or missing check ID: {cid}")
            all_checks.add(cid)
    for ref in references:
        relative = ref.split("#", 1)[0]
        if relative not in seen or not within(snapshot, relative).is_file():
            raise ValueError(f"Missing referenced snapshot document: {ref}")
    ordered = []
    pending = set(tasks)
    while pending:
        ready = sorted(t for t in pending if set(tasks[t]["depends_on"]) <= set(ordered))
        if not ready:
            raise ValueError("Task dependency cycle")
        ordered.extend(ready)
        pending.difference_update(ready)
    policy = registry["execution_policy"]
    if policy["initial_through"] != "M1" or set(policy["milestone_targets"]) != {f"M{i}" for i in range(1, 6)}:
        raise ValueError("Expected initial M1 scope and M1–M5 milestone targets")
    previous = set()
    for milestone in policy["milestone_targets"]:
        targets = policy["milestone_targets"][milestone]
        if not targets or len(targets) != len(set(targets)) or not set(targets) <= set(tasks):
            raise ValueError(f"Invalid scope targets for {milestone}")
        allowed = allowed_tasks(registry, milestone)
        if not previous <= allowed:
            raise ValueError("Scope milestones must grow monotonically")
        previous = allowed
    if allowed_tasks(registry, "M1") != {f"F{i:02}" for i in range(1, 9)}:
        raise ValueError("Initial scope must be exactly F01–F08")
    if allowed_tasks(registry, "M5") != set(tasks):
        raise ValueError("M5 must cover the full roadmap")
    return tasks, digest(manifest_path), len(members), len(all_checks), registry


def initial_state(tasks, snapshot_digest):
    return {
        "baseline": "R2",
        "snapshot_sha256": snapshot_digest,
        "execution_scope": {"through": "M1", "extensions": []},
        "tickets": {
            tid: {
                "status": "pending",
                "implementation_ref": None,
                "notes": [],
                "checks": {c["id"]: {"result": "pending"} for c in task["required_checks"]},
            }
            for tid, task in tasks.items()
        },
    }


def audit_state(state, tasks, snapshot_digest, repo_root, registry):
    if state.get("baseline") != "R2" or state.get("snapshot_sha256") != snapshot_digest:
        raise ValueError("State refers to another snapshot; explicitly reconcile it before continuing")
    records = state.get("tickets", {})
    if set(records) != set(tasks):
        raise ValueError("State ticket IDs do not match registry")
    scope = state.get("execution_scope", {})
    through = scope.get("through")
    allowed = allowed_tasks(registry, through)
    extensions = scope.get("extensions")
    if not isinstance(extensions, list):
        raise ValueError("State must retain scope extension history")
    previous = "M1"
    for extension in extensions:
        next_scope = extension["through"]
        if extension.get("from") != previous or int(next_scope[1:]) <= int(previous[1:]):
            raise ValueError("Invalid scope extension chain")
        allowed_tasks(registry, next_scope)
        evidence = within(repo_root, extension["authorization_path"])
        if not extension.get("recorded_at") or not evidence.is_file() or digest(evidence) != extension["authorization_sha256"]:
            raise ValueError("Scope extension lacks unchanged user-instruction evidence")
        if not evidence.read_text(encoding="utf-8").strip():
            raise ValueError("Empty scope authorization record")
        previous = next_scope
    if previous != through:
        raise ValueError("Scope changed without a recorded extension")
    if through != "M1" and any(records[t]["status"] != "complete" for t in allowed_tasks(registry, "M1")):
        raise ValueError("M1 must be complete before extending implementation scope")
    valid_statuses = {"pending", "in_progress", "blocked", "complete"}
    valid_results = {"pending", "passed", "failed", "blocked"}
    for tid, record in records.items():
        if record.get("status") not in valid_statuses:
            raise ValueError(f"Invalid status for {tid}")
        if tid not in allowed and (record["status"] != "pending" or record.get("implementation_ref")):
            raise ValueError(f"Work outside the recorded execution scope: {tid}")
        checks = record.get("checks", {})
        expected = {c["id"]: c for c in tasks[tid]["required_checks"]}
        if set(checks) != set(expected):
            raise ValueError(f"Check IDs differ for {tid}")
        for cid, check in checks.items():
            if check.get("result") not in valid_results:
                raise ValueError(f"Invalid result for {cid}")
            if tid not in allowed and check["result"] != "pending":
                raise ValueError(f"Check outside the recorded execution scope: {cid}")
            if check["result"] != "passed":
                continue
            required = ("evidence_path", "evidence_sha256", "environment", "evidence_kind")
            if any(not check.get(field) for field in required):
                raise ValueError(f"Passed check has missing evidence metadata: {cid}")
            if check["evidence_kind"] != expected[cid]["evidence_kind"]:
                raise ValueError(f"Wrong evidence category for {cid}")
            evidence = within(repo_root, check["evidence_path"])
            if not evidence.is_file() or digest(evidence) != check["evidence_sha256"]:
                raise ValueError(f"Missing or changed evidence for {cid}")
        if record["status"] == "complete":
            if not record.get("implementation_ref"):
                raise ValueError(f"Complete task lacks an implementation/diff reference: {tid}")
            if any(c["result"] != "passed" for c in checks.values()):
                raise ValueError(f"Complete task has unpassed checks: {tid}")
            unmet = [d for d in tasks[tid]["depends_on"] if records[d]["status"] != "complete"]
            if unmet:
                raise ValueError(f"Complete task has unmet dependencies: {tid}: {unmet}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "init", "next", "audit", "extend"))
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--through", choices=("M2", "M3", "M4", "M5"))
    parser.add_argument("--authorization-file", type=Path)
    args = parser.parse_args()
    tasks, snapshot_digest, count, check_count, registry = verify(args.snapshot.resolve())
    if args.command == "verify":
        print(json.dumps({"verified_files": count, "tickets": len(tasks), "required_checks": check_count,
                          "snapshot_sha256": snapshot_digest, "initial_execution_scope": "F01–F08, then M1 review",
                          "scope": "Document integrity, exact packet rendering and dependency checks only"}, indent=2))
        return
    if args.command in ("init", "audit", "extend") and args.state is None:
        raise ValueError("--state is required for init/audit/extend")
    if args.command == "init":
        args.state.parent.mkdir(parents=True, exist_ok=True)
        with args.state.open("x", encoding="utf-8") as handle:
            json.dump(initial_state(tasks, snapshot_digest), handle, indent=2)
            handle.write("\n")
        print(f"Initialized pending task state: {args.state}")
        return
    state = read_json(args.state) if args.state else initial_state(tasks, snapshot_digest)
    repo_root = args.repo_root.resolve()
    audit_state(state, tasks, snapshot_digest, repo_root, registry)
    records = state["tickets"]
    if args.command == "extend":
        if not args.through or not args.authorization_file:
            raise ValueError("extend requires --through and --authorization-file recording the actual user instruction")
        if any(records[t]["status"] != "complete" for t in allowed_tasks(registry, "M1")):
            raise ValueError("Finish M1 and its concrete product review before extending scope")
        scope = state["execution_scope"]
        if int(args.through[1:]) <= int(scope["through"][1:]):
            raise ValueError("extend must increase the authorized-through milestone")
        authorization = within(repo_root, str(args.authorization_file))
        if not authorization.is_file() or not authorization.read_text(encoding="utf-8").strip():
            raise ValueError("A nonempty saved user-instruction record is required")
        scope["extensions"].append({"from": scope["through"], "through": args.through,
                                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                                    "authorization_path": str(authorization.relative_to(repo_root)),
                                    "authorization_sha256": digest(authorization)})
        scope["through"] = args.through
        audit_state(state, tasks, snapshot_digest, repo_root, registry)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.state.parent, delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(state, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, args.state)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
        print(json.dumps({"through": args.through, "eligible_scope": sorted(allowed_tasks(registry, args.through)),
                          "limit": "Records the supplied instruction; cannot authenticate or invent user authorization"}, indent=2))
        return
    if args.command == "audit":
        print(json.dumps({"bookkeeping_valid": True,
                          "execution_scope": state["execution_scope"]["through"],
                          "complete": [t for t in tasks if records[t]["status"] == "complete"],
                          "limit": "Evidence truth and product quality still require review"}, indent=2))
        return
    allowed = allowed_tasks(registry, state["execution_scope"]["through"])
    ready = [t for t in tasks if t in allowed and records[t]["status"] in ("pending", "in_progress")
             and all(records[d]["status"] == "complete" for d in tasks[t]["depends_on"])]
    finished = all(records[t]["status"] == "complete" for t in allowed)
    checkpoint = state["execution_scope"]["through"] == "M1" and finished
    print(json.dumps({"ready": ready,
                      "execution_scope": state["execution_scope"]["through"],
                      "scope_complete": finished, "checkpoint_ready": checkpoint,
                      "blocked": {t: records[t].get("notes", []) for t in tasks if records[t]["status"] == "blocked"},
                      "instruction": ("STOP for the M1 product review. Later tickets need an explicit user scope extension."
                                      if checkpoint else "Deliver the completed authorized scope; do not infer a further extension."
                                      if finished else "Choose the first ready task within scope; blocked preparation is not completion.")}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, TypeError) as exc:
        print(f"Handoff check failed: {exc}", file=sys.stderr)
        sys.exit(1)
