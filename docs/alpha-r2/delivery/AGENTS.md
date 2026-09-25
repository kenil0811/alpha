# Alpha coding-agent instructions

Baseline R2 · handoff revision 3 · 25 September 2026. Install/reconcile these instructions in the authorized implementation repository; this planning artifact does not authorize unrelated repository changes.

Read the task packet and authoritative files named by the Project Index. Inspect repository status/branch and applicable instructions before edits. Preserve unrelated changes; a clean start is not permission for destructive resets. Use a clean worktree/branch when needed. A blank workspace needs no previous repository, branch or migration.

Build the platform that lets end users create workflows. Calorie/job requests and held-out cases are evaluations, not platform features. Do not add domain-specific schemas/screens/routes to Core or hand-edit generated results to pass generation gates. Build shared capabilities and reusable UX components. Follow Implementation Blueprint section 10: one maintained source, exact package/profile pins, read-only dependency reuse, isolated mutable state and verified per-App upgrades. Generated packages must not fork kit/SDK internals or mutate shared installations. One-off Tasks must not become hidden Apps; UI and tables are optional.

Implement one ready F-ticket at a time with relevant acceptance evidence. Add only exercised modules/dependencies. Follow the R2 stack and contract ownership; record an evidence-backed decision before a material change. Do not create a second competing plan in docs/PLAN.md; point it to the snapshot plan.

TASKS.json owns numbered packet steps/checks; Task_Packets.md is its verified readable rendering. Verify the snapshot, initialize/read local task_state.json, and continue through ready tasks within the recorded scope without routine confirmation. The initial scope is F01–F08 only; stop at M1 for review of the working creation experience. Later dependency-ready tickets remain inactive until an explicit user scope extension is recorded using the playbook. The helper validates bookkeeping only. No missing native/live/user evidence may be recorded as passed. Keep the snapshot immutable and local implementation status/evidence under docs/development; export it for project reconciliation rather than claiming live planning-project access.

Keep generated code outside trusted Core, UI outside native authority, user data outside code versions, and credentials outside generated packages/logs. Recheck current grants at dispatch. Code rollback is not data rollback. Window close preserves runtime; explicit quit stops it; missed work needs manual retrigger with no automatic catch-up.

Test real bindings, SQLite concurrency, worker lifecycle and external-outcome uncertainty where applicable. Mocks cannot satisfy live/native gates. Preserve failures, budgets and complete attempt history; never loosen assertions, hardcode outcomes, fabricate evidence or claim a preview proves operation. Independent expected results must not be derived from the implementation under test.

Do not run paid/model/external actions beyond existing authorization and configured budgets. Finish authorized reversible work autonomously. Ask only for material missing context/access/authorization, explaining exactly what depends on it. No repeat confirmation for already-authorized scope. No external release with unqualified containment or credential protection.

Store task notes and evidence under docs/development/tasks and docs/development/evidence. Report changes, meaningful tests, limitations and next ready ticket. Mark implementation complete only with evidence. A document or fake harness does not establish product readiness.
