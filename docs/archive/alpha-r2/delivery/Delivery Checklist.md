# Delivery checklist

Baseline R2 · handoff revision 3 · 25 September 2026. Documentation is reconciled; **no R2 implementation completion is claimed**. This file is the planning project's reconciled delivery view. In a coding checkout, docs/development/task_state.json and its evidence own operational progress; the implementation plan owns acceptance details.

| Ticket | Result | Status | Evidence |
|---|---|---|---|
| F01 | Desktop/Core/worker path | Pending | — |
| F02 | Real builder and model route | Pending | — |
| F03 | UI boundary and isolation feasibility | Pending | — |
| F04 | Request to SolutionBrief | Pending | — |
| F05 | Records/artifacts/model SDK | Pending | — |
| F06 | Shared UX kit | Pending | — |
| F07 | Candidate verification and repair | Pending | — |
| F08 | Generated result delivery/reopen | Pending | — |
| F09 | Concurrency and ingestion integrity | Pending | — |
| F10 | Versions and data-preserving change | Pending | — |
| F11 | One-off outputs/actions | Pending | — |
| F12 | Interruption recovery | Pending | — |
| F13 | HTTP/file connections | Pending | — |
| F14 | Dedicated browser sessions | Pending | — |
| F15 | Effects/approval/reconciliation | Pending | — |
| F16 | Generated job-flow evaluation | Pending | — |
| F17 | Local schedules | Pending | — |
| F18 | Evidence-based repair | Pending | — |
| F19 | Generalization cohort | Pending | — |
| F20 | Qualified execution boundary | Pending | — |
| F21 | Privacy and restore | Pending | — |
| F22 | Signed Mac installation/update | Pending | — |
| F23 | Nontechnical pilot | Pending | — |
| F24 | Private-alpha decision | Pending | — |

The initial authorized engagement is F01–F08 through M1. G0 (F01–F03), G1, G2, G3, G4 and G5 are all pending. Completion of F01–F08 leads to product review; later work requires an explicit scope extension. G0 is technical feasibility; G1 is the first product-value gate. Gate numbers and ticket dependencies are defined in Prototype_Scope_and_Acceptance.md.

For each completed ticket record commit, snapshot hash, environment/toolchain, fixture/prompt IDs, commands/exit codes, sanitized evidence paths, open limitations and reviewer. Distinguish unit/control, integration, native, live-model, live-source, rendered-UX and user-study evidence. Never substitute one category silently for another. Use Pending, In progress, Blocked, or Complete; include a precise blocker and next action when blocked.

Agents coding outside this project maintain docs/development/task_state.json using TASKS.json and the handoff helper. That local record tracks actual implementation progress until it is reconciled into this project checklist. The agent must not assume live access or claim remote updates. Task_Packets.md defines numbered required checks; completed local state must reference real evidence for each one.
