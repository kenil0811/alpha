# Start here — Alpha from a blank workspace

Clean-start R2 · handoff revision 3 · 25 September 2026. This complete planning snapshot needs no previous chat, codebase, branch or migration. Product implementation and all native/live/user gates remain pending.

Build the platform through which nontechnical end users create their own work solutions. Apps, one-off Tasks, artifacts and background workflows are valid outcomes. Calorie/job examples are evaluation requests, never manually implemented Core features.

## Initial engagement

Implement **F01–F08 only**, then stop at **M1/G1 for review of the working creation experience**. Continue routine eligible work autonomously within that scope. Later tickets remain in the bundle for continuity, but dependency readiness does not authorize them. If required access is missing, record the blocked checks and continue independent work within scope. Do not replace native/live evidence with mocks.

## Bootstrap

1. Inspect the authorized workspace and applicable instructions. Preserve unrelated files. A blank workspace is sufficient; do not invent a remote or publish the project.
2. Extract this ZIP into `docs/alpha-r2` without overwriting an unrelated directory. Run the helper below from the implementation repository root with Python 3.10 or newer. This stdlib helper is independent of the planned product Python runtime.
3. Read `delivery/AGENTS.md` and reconcile it with repository instructions. Read `delivery/AI_Coding_Agent_Playbook.md`, then the common reading list in `delivery/TASKS.json` and references for the current ticket. `00 Project Index.md` maps canonical owners.
4. Implement the first eligible ticket. `TASKS.json` owns exact steps/checks; `Task_Packets.md` is its verified readable rendering. The implementation plan owns milestones, scope and gates. Create only code exercised by a ticket.

```bash
python3 docs/alpha-r2/delivery/agent_handoff.py verify docs/alpha-r2
python3 docs/alpha-r2/delivery/agent_handoff.py init docs/alpha-r2 --state docs/development/task_state.json
python3 docs/alpha-r2/delivery/agent_handoff.py next docs/alpha-r2 --state docs/development/task_state.json --repo-root .
python3 docs/alpha-r2/delivery/agent_handoff.py audit docs/alpha-r2 --state docs/development/task_state.json --repo-root .
```

Run `init` only once; it refuses to overwrite existing state. Later sessions read and audit that state. `next` without a state starts from all-pending. `verify` checks snapshot hashes, exact packet rendering, references and dependencies. `audit` checks scope, completion prerequisites and evidence-file hashes/categories. Neither runs product tests, certifies evidence truth nor grants permission.

F01 implements the actual `just verify-ticket F01` dispatcher; it does not already exist because this bundle names it. Other tickets register their real checks. Unimplemented/unknown recipes must fail, and missing native/live/user checks stay pending.

## Shared foundation

Read **Implementation Blueprint section 10** for shared services, SDK/UI/module packages, immutable dependency profiles and verified upgrades. **Current Release Specification section 11** owns their serialized fields. Use uv and pnpm for managed dependency installation/cache reuse, separate worker processes and private writable data. No mutable shared App environment, copied platform internals or new registry service. Shared code does not imply shared account/data authority.

## Progress and review

Keep this snapshot immutable. `docs/development/task_state.json` and its evidence own progress in the implementation checkout; the bundled Delivery Checklist is the planning project's pending/reconciled view. Do not claim it was updated remotely. Record session handoffs and decisions under docs/development. An amended snapshot needs explicit evidence reconciliation, not automatic carryover of passes.

At M1, deliver the concrete G1 demo and evidence packet defined by the plan/playbook. The helper returns no later ready work. After an actual user instruction extends scope, save its wording/date/source reference to a new instruction file and use the command below with the milestone actually authorized. This example enables the entire remaining roadmap; do not run it without that instruction.

```bash
python3 docs/alpha-r2/delivery/agent_handoff.py extend docs/alpha-r2 --state docs/development/task_state.json --repo-root . --through M5 --authorization-file docs/development/scope-authorization.md
```

Available later scopes are M2, M3, M4 and M5. The helper includes their transitive prerequisites, including F20/F21 for M3/M4. Preserve each instruction file unchanged; use a new file for another extension. The helper records references, not proof that the user gave authorization. No routine per-ticket confirmation is needed.

`delivery/Agent_Start_Prompt.md` is the pasteable bootstrap prompt. `MANIFEST.json` identifies exact bytes; `PLANNING_AUDIT.json` reports handoff checks only. Duplicate reader/first-task/access notes, reconciliation history, old code, retired machine schemas, examples, mockups and previous proof archives are excluded. No file outside this bundle is needed to understand what to build.
