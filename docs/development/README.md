# docs/development

Operational implementation records for the Alpha checkout. The planning snapshot in `docs/alpha-r2`
is immutable; everything mutable lives here.

- `task_state.json` — helper-maintained ticket/check state (see delivery/AI_Coding_Agent_Playbook.md).
- `tasks/` — per-ticket notes and session handoffs.
- `evidence/` — per-check evidence files referenced by task_state.json (hashed).
- `decisions/` — evidence-backed implementation decisions.
