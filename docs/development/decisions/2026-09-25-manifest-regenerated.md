# Decision: MANIFEST.json regenerated from delivered bundle bytes

Date: 2026-09-25. Recorded by the coding agent (self-review).

The delivered Alpha_Agent_Context bundle (clean-start R2, handoff revision 3) did not contain
`MANIFEST.json`, although START_HERE.md references it and `agent_handoff.py verify` requires it.
PLANNING_AUDIT.json reports 35 verified manifest files, which matches the 35 delivered documents
plus PLANNING_AUDIT.json itself (36 hashed entries).

Action: generated `docs/alpha-r2/MANIFEST.json` from the exact delivered bytes (SHA-256 per file).
No delivered document was modified. A stray `delivery/__pycache__` created by an import check was
deleted before hashing. The resulting snapshot digest reported by `verify` is
`a7dc7105c70a9b7def5ab60df6c77eabfd618128136dfc5cf7eb521999a71ef1`; task_state.json is bound to it.

Consequence: integrity checks prove the snapshot has not changed since installation here, not
that it matches the planning project's original manifest. If the original MANIFEST.json is
supplied later, reconcile explicitly (compare hashes, replace, re-init state only if digests differ).
