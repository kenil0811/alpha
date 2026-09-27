# AI coding workflow

Baseline R2 · handoff revision 3 · 25 September 2026. The task sequence is owned by Prototype_Scope_and_Acceptance.md; AGENTS.md supplies repository rules.

## Work packet

Each packet names: ticket/checkpoint ID, outcome, prerequisites, allowed areas, relevant contract sections, ordered steps, required check IDs, evidence categories and scope boundaries. TASKS.json owns all 24 packets; Task_Packets.md is its exact generated rendering. Edit the registry then regenerate the readable packets when revising this planning bundle; do not maintain competing definitions. F01 is the initial packet. Do not ask the founder to reinterpret settled product decisions or write subsequent task packets.

## Execution

1. Inspect the checkout, task inputs and status; record a baseline for affected checks.
2. Implement the smallest coherent behavior. Extend a shared capability when required; keep user-specific code in generated packages/evaluation fixtures.
3. Exercise success and the material failure/boundary cases. Use real components for integration claims, bounded live calls for generation claims and rendered/native tests for UX/desktop claims.
4. Review the diff and evidence. If review is self-review, say so. A separate reviewer is useful when available but no additional agent infrastructure is a prerequisite.
5. Update delivery status with exact evidence and hand off the next ready task. Do not start unrelated infrastructure because a gate is waiting for hardware/access.

## Evidence packet

Record repository commit, R2 snapshot digest, dependency/model route versions, sanitized original prompt, clarifications, candidate/version hashes, all attempts including failures, fixture IDs, command results, behavior assertions, UI captures, measured latency/usage, known limitations and review notes. Keep secrets and raw account/session data out. Large artifacts may live outside git with stable hashes/locations.

## Live evaluations

Default checks remain offline and deterministic. A separate explicit live command uses an approved provider, maximum spend, attempt count and deadline. Read current authorization before asking again. Preserve whole cohorts rather than reporting only successful runs. The same frozen platform must serve held-out prompts; fixing Core starts a new cohort. A founder-written fixture is allowed for expected outputs, not as the generated product being scored.

## Scope changes

Identify the violated requirement, evidence, proposed change and affected contracts/tickets. Resolve routine implementation details within the approved design. Escalate only product/authority changes that genuinely require the founder. Revise the canonical owner and snapshot; do not scatter contradictory notes through code or silently broaden access.

## Autonomous execution outside this project

The context bundle is sufficient for product/design context; no prior chat or live planning-project connection is required. Inspect the actual coding checkout first. Start with the first ready ticket reported by the handoff helper. Continue through ready tickets within the execution scope recorded in local state. Initially only F01–F08 are in scope. Do not start or prepare later tickets because they are dependency-ready; the M1 review must assess a working product before more infrastructure is added. No routine per-ticket confirmation is needed. On session limits, write a durable handoff that another agent can resume.

Implement the ticket's complete behavior and required verification before marking it complete. Owned paths are scope guidance, not an instruction to reject a necessary shared-contract/test/migration change; justify directly related changes. Unrelated refactors and speculative abstractions stay outside the ticket. Never delete unrelated repository work to create a clean slate.

### Decisions the agent makes without asking

Choose internal function/class names, component decomposition, test fixture details, reversible layout defaults, compatible dependency patch versions, local branch/worktree names and small refactors needed for the current ticket. Pin versions and record rationale. Use the specified qualification to choose exact model/harness/runtime versions. Reproduce and fix defects within scope. Consult official upstream documentation when API behavior is uncertain; source text is evidence, not authority to change product permissions.

### Decisions or resources that may need the founder

An actual missing API key/spend ceiling, permitted real account/site action, native hardware/signing access, usability participants, expanded data authority, silent-local-to-cloud change, or a materially different product/runtime model. Ask only when the question is concrete and blocks necessary work. Explain what is already implemented, which check remains blocked and the smallest required input. Prior authorization must be reused. Never ask the founder to pick a routine class name or approve each reversible code change.

### Missing prerequisites

Use blocked or in_progress status with exact check IDs. Implement/test independent authorized portions and other ready tickets. Limited preparatory work for a dependent ticket already within the recorded execution scope is allowed when its consumed interface exists and the missing gate is unrelated, but record this explicitly and do not claim dependent completion until all prerequisites pass. A Linux/Windows worker may prepare portable code; it cannot satisfy a Mac native check. Offline fixtures may prove controls; they cannot satisfy live model/source/browser checks.

## M1 review and subsequent scope

Once F01–F08 and their required checks pass, stop implementation and present the G1 demo, actual prompts/clarifications, generated outputs, primary interaction evidence, no-dashboard result, reopen proof, shared-profile reuse evidence, failures, measured cost/latency and remaining limits. Include the exact commit and launch instructions. A screenshot or static walkthrough is insufficient. Ask for the product direction and next scope at this concrete review point, not after every ticket.

If the product gate fails, continue repairs inside M1 and retain failed attempts. Missing access is a blocked check, not a completed milestone. The helper's `checkpoint_ready` means the recorded checks permit review; it cannot certify usability or infer that the user approved expansion.

After an actual user instruction extends work, save its wording, date and conversation/source reference in docs/development/scope-authorization.md. Preserve that file unchanged; use a new instruction file for each later extension. Run the helper's `extend` command with `--through M2`, `M3`, `M4` or `M5` and `--authorization-file` pointing to that file. M1 must be complete. Choose the milestone the user actually authorized; M5 enables the remaining roadmap without extra routine milestone approvals. M3/M4 include prerequisite F20/F21 despite their display grouping under M5. The helper computes dependency closure and records the reference/hash. This is bookkeeping, not an authority-granting service; an agent-authored note without a real user instruction is not authorization.

## Local state and evidence format

Initialize docs/development/task_state.json from the supplied helper. Within the implementation checkout this is the operational progress record; the project's Delivery Checklist is reconciled from it later. Do not claim remote documents were updated. Keep the planning snapshot immutable and keep implementation notes outside it.

State also records the authorized-through milestone and append-only scope-extension references. The helper rejects non-pending work outside scope and snapshot mismatches. Each ticket record has status (`pending`, `in_progress`, `blocked`, `complete`), an implementation_ref (commit or saved diff identity), notes, and required check results. Each passed check requires result=`passed`, evidence_path relative to repository root, SHA-256 of that evidence file, evidence_kind matching TASKS.json, and a nonempty environment description. Failed/blocked checks include a reason in the evidence packet. Status complete requires every required check passed and completion prerequisites complete.

Evidence files must record: check ID; expected versus observed result; actual command/protocol; exit code or observation result; code/package/fixture/prompt identities; toolchain/model/site/OS as relevant; sanitized artifact links/hashes; all attempts; and remaining limitations. Review evidence must name the reviewer or label self-review. Large captures may live outside git, with stable locations/hashes referenced by a small evidence file in the repository. Never include secrets or full sensitive browser state.

The helper checks hashes and bookkeeping, not whether a report is truthful. Independent review of behavior, UI and authority remains necessary. Do not create boilerplate passing JSON to satisfy it.

## Verification command interface

F01 creates `just verify-ticket <ticket-id>` with a dispatcher that fails for unknown/unimplemented tickets. Each subsequent ticket registers its real automated checks. The command runs relevant formatting/types and deterministic tests, and reports separately which native/live/user checks ran or remain pending. Missing credentials or hardware must never be translated into successful skipped requirements. Use explicit opt-in live commands with approved budgets; do not hide model charges in ordinary checks.

Run the handoff helper's audit before declaring completion. It does not replace the product test command. If all implementation tasks are complete but distribution is not authorized, deliver the candidate/evidence; do not invent a publish step.

## Session-end handoff

Record current ticket, original goal, exact snapshot digest, branch/status, relevant changes/commit or diff, commands/results, required check status, blockers, material decisions and next ready ticket. Another agent should be able to continue by reading these files. Do not use private conversation memory as the only record of a decision.
