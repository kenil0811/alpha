# Per-ticket execution packets

Clean-start R2 · handoff revision 3 · 25 September 2026. Generated from TASKS.json; do not edit independently.

The implementation plan owns scope and gates. TASKS.json owns ordered packet steps and required checks. Product and specification owners define behavior. The helper verifies this rendering against the registry.

## Rules for every packet

Read the common sources in TASKS.json and the packet's references. #N denotes a numbered section; #Fxx denotes a ticket heading, not a guaranteed Markdown anchor. Proposed paths are ownership guidance, not existing files. Create only exercised code; justify directly required shared-contract/test changes.

Initially implement F01–F08 only and stop at M1 for product review. Later tickets are fully specified for continuity but require an explicit scope extension under the playbook. Dependency readiness does not override this boundary.

Every numbered check is required for completion. Record expected/observed behavior, actual command or observation protocol, result, exact environment and relevant code/package/input identities. Integration uses real components; native requires the supported Mac; live_model/live_source require actual authorized calls; user_study requires people. Review is not a substitute for those checks.

F01 creates just verify-ticket F01 and the real dispatcher; unknown/unimplemented recipes fail. Subsequent tickets register meaningful automated checks and separately report native/live/user requirements. Missing access is blocked, never a fabricated pass. Follow AI_Coding_Agent_Playbook.md for evidence, local state and scope. The helper checks bookkeeping, not evidence truth or product quality.

## F01 — Desktop/Core/worker bootstrap

**Completion prerequisites:** none.
**Owned areas:** apps/desktop; services/core; packages/contracts; tests/integration; justfile; toolchain files.
**Read:** architecture/Implementation Blueprint.md; specifications/Current Release Specification.md#6.

**Implement in this order:**

1. Create the minimal monorepo with pinned uv/Python and pnpm/Node workspace toolchains, committed locks and exercised just commands; record actual OS/toolchain versions. Add just verify-ticket F01 with a dispatcher that fails for unknown/unimplemented tickets.
2. Implement the trusted shell and authenticated loopback Core transport; create durable Run/event tables and one synthetic worker profile.
3. Implement native window-close versus explicit-quit behavior, process-tree cancellation and restart reconciliation for this narrow path.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F01.C01 | Desktop/Core starts using bundled Python; the supplied payload runs and survives reopen. | native |
| F01.C02 | Worker error and cancellation produce honest durable state; descendants terminate. | native |
| F01.C03 | Missing/wrong IPC credentials and unapproved origins fail. | integration |
| F01.C04 | Core/worker interruption is visible after restart; window close and explicit quit have distinct behavior. | native |
| F01.C05 | A clean platform dependency install obeys committed locks and exact tool versions; changed locks or an unknown/unimplemented ticket verification recipe fail visibly. No per-App dependency infrastructure is scaffolded ahead of F05. | integration |

**Scope boundary:** No model integration, complete navigation system, generated business app or empty future modules.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F01`. Required pending checks block completion.

## F02 — Real builder and model route

**Completion prerequisites:** F01.
**Owned areas:** services/core/alpha/builds; services/core/alpha/models; workers/builder; packages/contracts; tests/qualification.
**Read:** specifications/contracts/Builder Harness Interface.md; specifications/Current Release Specification.md#4; architecture/Current Architecture Decisions.md.

**Implement in this order:**

1. Implement ModelGateway route/token/budget plumbing and a private OpenCode process/session adapter; use an explicitly authorized BYOK route.
2. Generate a small pure transformation package from a fresh plain-language prompt and invoke its actual generated function; full record services arrive in F05.
3. Exercise build failure, cancel with descendants, token/usage reporting and restart cleanup; pin the exact working route or take the documented bounded fallback.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F02.C01 | A real paid-or-authorized model invocation produces source that compiles and returns independently checked outputs. | live_model |
| F02.C02 | Failed builder/check combinations cannot produce a successful candidate. | integration |
| F02.C03 | Cancel cleans descendants and reconnect/restart does not revive obsolete work. | native |
| F02.C04 | Private config and scoped gateway token are used; source/logs omit durable secrets and all attempts/usage are retained. | integration |

**Scope boundary:** Do not implement two complete harnesses or infer success from provider prose. A fake remains a control fixture only.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F02`. Required pending checks block completion.

## F03 — UI boundary and sandbox feasibility

**Completion prerequisites:** F01.
**Owned areas:** apps/desktop; packages/ui-bridge; workers; tests/qualification.
**Read:** specifications/contracts/App UI Bridge.md; architecture/Security Privacy and Data Boundaries.md; architecture/Implementation Blueprint.md#4.

**Implement in this order:**

1. Implement a minimal generated React fixture in the real Tauri unprivileged surface and a bound MessageChannel.
2. Exercise two synthetic owner/session grants, invalid message shapes, navigation/revocation and native-token access attempts.
3. Probe a pinned sandbox candidate against canary files, symlinks, child processes and network paths; record gaps for F20.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F03.C01 | Unprivileged UI cannot invoke native/Core authority or use another owner/session. | native |
| F03.C02 | Navigation/release/session changes invalidate stale bridge authority; malformed requests fail. | integration |
| F03.C03 | Actual Mac sandbox probes and cleanup results, including failures, are recorded with a viable next profile decision. | native |

**Scope boundary:** Feasibility is not full containment certification. Use nonsensitive fixtures; do not claim F20 complete.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F03`. Required pending checks block completion.

## F04 — Conversation to SolutionBrief

**Completion prerequisites:** F02.
**Owned areas:** services/core/alpha/assistant; packages/contracts; apps/desktop/src.
**Read:** product/Current Release UX Specification.md#3; specifications/Current Release Specification.md#2; architecture/Resource Context and Integration Architecture.md.

**Implement in this order:**

1. Expose currently available capabilities and unmet prerequisites; route each request to answer, Task or reusable App.
2. Implement structured brief creation/revision, selected-context lineage, material clarification and reversible defaults.
3. Show a short user-facing interpretation and persist corrections without turning setup into a schema-design questionnaire.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F04.C01 | Tracker, artifact and unsupported-capability requests route appropriately through the real model loop. | live_model |
| F04.C02 | Clarification responses revise the brief with assumptions/provenance retained; no unnecessary App is created. | integration |
| F04.C03 | User-facing setup is understandable and can be corrected without technical vocabulary. | rendered_ui |

**Scope boundary:** Do not invent credentials, grant authority from a brief or ask users to choose database/UI implementation details.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F04`. Required pending checks block completion.

## F05 — Record/artifact/model SDK

**Completion prerequisites:** F01, F02, F04.
**Owned areas:** services/core/alpha/data; services/core/alpha/artifacts; services/core/alpha/models; packages/app-sdk; workers/app; packages/contracts; services/core/alpha/execution.
**Read:** specifications/Current Release Specification.md#8; architecture/Domain and Persistence Model.md; architecture/Implementation Blueprint.md#8; architecture/Implementation Blueprint.md#10; specifications/Current Release Specification.md#11.

**Implement in this order:**

1. Implement minimum App ownership/schema records plus scoped record/query/aggregate operations and artifact staging/sealing.
2. Implement the worker SDK and real generated-function runner; route model calls through the scoped gateway with structured outputs.
3. Validate inputs/results and support real persistence/reopen, local transaction rollback and cross-owner rejection.
4. Build the default immutable App/Task Python profile using managed uv installation; publish and inventory it once, launch workers with its exact interpreter and isolate scratch/import paths. Run two neutral App fixtures against the same installed profile with distinct records/credentials.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F05.C01 | Actual worker/SDK operations validate, save, query, aggregate and reopen records correctly. | integration |
| F05.C02 | Wrong-owner operations, invalid values and unsafe/unbounded queries fail. | integration |
| F05.C03 | Artifacts have correct bytes/digests/provenance and bounded model results are correctable rather than presented as facts. | integration |
| F05.C04 | Two separate App worker processes reuse the same exact installed SDK/runtime profile while records, broker tokens, module globals and writable scratch remain distinct. Restart uses the pinned installation without a runtime install; functional proof is not F20 containment qualification. | integration |

**Scope boundary:** No job/calorie-specific tables or rules, raw SQL/native paths in generated code, or claim that F09 concurrency tests already passed.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F05`. Required pending checks block completion.

## F06 — Reusable interaction kit

**Completion prerequisites:** F03, F04.
**Owned areas:** packages/ui-kit; packages/ui-bridge; templates/app; tests/ui.
**Read:** product/Current Release UX Specification.md#5; product/Current Release UX Specification.md#10; specifications/contracts/App UI Bridge.md; architecture/Implementation Blueprint.md#10.

**Implement in this order:**

1. Implement tokens and the smallest complete quick-entry, form, record/review, detail, trend and feedback components.
2. Document composition/use contracts and accessible keyboard behavior; expose documentation/examples to the builder.
3. Create pattern references with neutral fixture data and verify empty/populated/loading/failure/narrow states.
4. Build one exact UI-kit/bridge package in the managed pnpm UI profile. Templates and two neutral compositions import those packages rather than copy implementation; preserve exact pins in build evidence.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F06.C01 | Keyboard entry/correction, filtering and failed-save recovery work through the bridge. | rendered_ui |
| F06.C02 | Supported widths, long labels, empty states and accessible names/focus have no blocking defects. | rendered_ui |
| F06.C03 | Reference components contain reusable behavior and no exemplar-domain platform shortcuts. | review |
| F06.C04 | Two neutral UI compositions build and run using the same pinned kit/bridge source packages with no vendored forks; no remote runtime import or App-specific Node server is introduced. Compiled asset duplication is allowed. | integration |

**Scope boundary:** No mandatory UI DSL, generic CRUD-only quality bar or finished founder-written example app.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F06`. Required pending checks block completion.

## F07 — Candidate verification and bounded repair

**Completion prerequisites:** F02, F05, F06.
**Owned areas:** services/core/alpha/builds; workers/validator; templates/app; packages/contracts; tests/integration; evals.
**Read:** specifications/Current Release Specification.md#3; specifications/Current Release Specification.md#4; specifications/contracts/Package Layout.md; specifications/Current Release Specification.md#11; architecture/Implementation Blueprint.md#10.

**Implement in this order:**

1. Validate source paths/dependencies/schemas and resolve actual action handlers inside the disposable worker.
2. Run independently owned behavior checks, build assets, launch/interact with UI and retain detailed reports against exact bytes.
3. Feed failed checks to bounded builder repair, enforce attempt/time/cost limits and seal only a verified candidate.
4. Resolve and seal the platform-owned dependency manifest, full package closure, exact locks and profile digests. Validate and invoke against the same installed profile; unsupported extra dependencies produce a bounded qualification request rather than mutation of a common environment.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F07.C01 | Missing handler, false persistence and contradictory builder/validator outcomes are rejected. | integration |
| F07.C02 | Primary interaction, saved outputs and rendered states are actually exercised, with failing UI withheld from ready status. | rendered_ui |
| F07.C03 | Real builder repair fixes a reproducible case or honestly stops at limits; every attempt is retained. | live_model |
| F07.C04 | An undeclared dependency, changed lock/artifact, incompatible profile or substituted runtime fails validation/activation. Sealed outputs contain exact pins and no credentials, mutable environment or ambient Core imports; worker startup never resolves or installs packages. | integration |

**Scope boundary:** Candidate-authored tests are supplemental. Never alter independent expectations to match generated code.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F07`. Required pending checks block completion.

## F08 — User creation and delivery loop

**Completion prerequisites:** F04, F05, F06, F07.
**Owned areas:** services/core/alpha/assistant; services/core/alpha/solutions; apps/desktop/src; evals.
**Read:** delivery/Prototype_Scope_and_Acceptance.md#F08; product/Current Release UX Specification.md#4; specifications/Current Release Specification.md#5.

**Implement in this order:**

1. Join brief, build, checks, preview and activation with stable App/version/data identities.
2. Expose a useful generated UI or shell-provided no-custom-UI result and retain working state on restart.
3. Freeze platform code and run G1 using ordinary calorie, different workflow and held-out local requests.
4. Collect shared-profile reuse evidence from at least two actually generated results, including separate data/scratch and one-worker cancellation. Assemble the concrete G1 review packet and stop at M1; later ready tickets remain out of scope.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F08.C01 | All G1 requests go through actual generation and primary use without developer edits to generated source. | live_model |
| F08.C02 | Generated interfaces are usable and at least one reusable result needs no custom dashboard. | rendered_ui |
| F08.C03 | Active package/data and user-created results reopen correctly; preview/sample data is honestly labeled. | integration |
| F08.C04 | At least two G1 generated results run with the same installed SDK/runtime profile and independent saved data/scratch; failure or cancellation of one does not corrupt or terminate the other. The review packet includes exact launch instructions and all G1 outcomes. | integration |

**Scope boundary:** Scheduling/external access can be absent here. Choose held-out requests inside the currently qualified local capability envelope.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F08`. Required pending checks block completion.

## F09 — Concurrency and ingestion integrity

**Completion prerequisites:** F05, F08.
**Owned areas:** services/core/alpha/data; packages/app-sdk; tests/integration.
**Read:** architecture/Domain and Persistence Model.md; specifications/Current Release Specification.md#8.

**Implement in this order:**

1. Implement CAS revisions in the SQL mutation, local transaction boundaries and idempotency-key payload checks.
2. Implement unique ingestion identity and explicit source projection versus user override merge operations.
3. Exercise two real SQLite writers and repeated refresh/retry, including conflicting payloads.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F09.C01 | Concurrent same-revision updates produce exactly one commit and one conflict. | integration |
| F09.C02 | Duplicate ingestion/retry does not duplicate data; changed payload with reused key fails. | integration |
| F09.C03 | Refresh preserves user notes/status/overrides and rollback on local transaction error works. | integration |

**Scope boundary:** A pre-read revision comparison or mock repository is not enough evidence.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F09`. Required pending checks block completion.

## F10 — Versions and data-preserving change

**Completion prerequisites:** F07, F08, F09.
**Owned areas:** services/core/alpha/solutions; services/core/alpha/data; apps/desktop/src; tests/integration; evals.
**Read:** specifications/Current Release Specification.md#5; specifications/contracts/Release Resolution Record.md; architecture/Domain and Persistence Model.md; architecture/Implementation Blueprint.md#10.

**Implement in this order:**

1. Implement settings-only versus code-change paths, candidate copies and schema compatibility checking.
2. Implement migration fencing/journal/backup for the supported additive profile and CAS activation.
3. Generate a change, inject a bad candidate and exercise stale activation and incompatible rollback.
4. Inventory consumers of a shared SDK/module/UI change, publish a new immutable profile, and rebuild per-App candidates. Inject one failing consumer while another passes; activate independently and retain old profiles for existing runs and compatible rollback.
5. Distinguish compatible shared-service patches from interface-breaking updates. Qualify compatibility before a central patch; reject unsupported consumers or pause them visibly without silently changing their interface.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F10.C01 | Generated field/view change preserves existing records and user decisions. | live_model |
| F10.C02 | Failed/stale candidates cannot replace the current release; activation races resolve correctly. | integration |
| F10.C03 | Migration crash recovers; incompatible code rollback is refused and data restore remains a separate explicit action. | integration |
| F10.C04 | A common dependency fix is made once and reaches two identified consumers through separate candidates. One deliberately failed candidate leaves its release/data unchanged; the passing candidate activates. A preexisting run keeps its original profile and compatible code rollback preserves current data. | integration |
| F10.C05 | A compatible provider/service patch passes consumer contract tests; a breaking interface change cannot silently run an old consumer against the new contract. Retained compatibility or explicit pause with repair is observable. | integration |

**Scope boundary:** Do not execute arbitrary generated migration SQL in Core or silently restore an old database.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F10`. Required pending checks block completion.

## F11 — One-off outputs

**Completion prerequisites:** F04, F05, F07.
**Owned areas:** services/core/alpha/assistant; services/core/alpha/execution; services/core/alpha/artifacts; workers/parser; apps/desktop/src.
**Read:** specifications/Current Release Specification.md#6; architecture/Input Memory and Procedure Architecture.md; product/Current Release UX Specification.md.

**Implement in this order:**

1. Implement distinct Task revisions/attempts and the shared execution envelope without a forged release.
2. Add selected text/CSV plus one qualified document parser, isolated for complex formats.
3. Deliver a provenance-linked artifact with preview/export, retry lineage and cancellation.
4. Ephemeral generated Task computation reuses an exact qualified runtime profile with a Task-owned lease and scratch. Broker-only Tasks need no generated-code installation or hidden App.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F11.C01 | Ordinary document request produces a correct downloadable result without creating an App. | live_model |
| F11.C02 | Parser budgets/path/archive boundaries, malformed inputs and cancellation behave as specified. | integration |
| F11.C03 | Output bytes/provenance and separate retry attempts survive reopen. | integration |

**Scope boundary:** Do not claim audio synthesis, arbitrary document support or browser actions before their providers qualify.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F11`. Required pending checks block completion.

## F12 — Durable interruption recovery

**Completion prerequisites:** F08, F09, F10, F11.
**Owned areas:** services/core/alpha/execution; services/core/alpha/solutions; apps/desktop/src; workers; tests/integration.
**Read:** specifications/Current Release Specification.md#6; specifications/contracts/Run Event Kernel.md; architecture/Deployment and Execution Architecture.md.

**Implement in this order:**

1. Implement run transitions/events, stable step keys, worker leases, long waits and scoped re-entry.
2. Reconcile abandoned workers/build promotions and preserve committed outputs after Core/worker failure.
3. Inject failures at meaningful boundaries and execute the G2 scenarios.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F12.C01 | Restart retains correct state/data and interrupted/waiting work is visible. | integration |
| F12.C02 | Step reuse with unchanged input avoids duplicate committed work; changed input fails key matching. | integration |
| F12.C03 | Actual Mac process cleanup and restart behavior agree with durable status. | native |

**Scope boundary:** No automatic arbitrary Python stack resume or claim of exactly-once external effects.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F12`. Required pending checks block completion.

## F13 — HTTP/file providers

**Completion prerequisites:** F09, F11, F12.
**Owned areas:** services/core/alpha/capabilities; services/core/alpha/connections; apps/desktop/src; packages/app-sdk; tests/integration.
**Read:** specifications/contracts/HTTP Action Profile.md; architecture/Resource Context and Integration Architecture.md; specifications/Current Release Specification.md#7.

**Implement in this order:**

1. Implement CapabilityCatalog/profile discovery, bounded read dispatch and current grant/connection resolution.
2. Implement selected file handles, trusted credential injection, destination/redirect/address limits and provenance.
3. Use a real public source and a controlled credentialed API with synthetic tokens; defer personal accounts until F20/F21.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F13.C01 | Fresh public data and controlled authenticated results are correct, scoped and carry provenance. | live_source |
| F13.C02 | Revoked grants, wrong owners, redirected private targets and oversized responses fail. | integration |
| F13.C03 | Generated code/logs do not receive secrets or unrestricted paths; writes remain gated. | integration |

**Scope boundary:** No seed data passed off as retrieval, unknown protocol support or real personal-account testing before protection.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F13`. Required pending checks block completion.

## F14 — Dedicated browser provider

**Completion prerequisites:** F03, F12, F13.
**Owned areas:** workers/browser; services/core/alpha/capabilities; apps/desktop; tests/browser.
**Read:** architecture/Resource Context and Integration Architecture.md; specifications/Local_Automation_and_Platform_Extension_Profile.md; architecture/Security Privacy and Data Boundaries.md.

**Implement in this order:**

1. Implement managed contexts, source-scoped navigation/inspection, selected transfer and visible takeover.
2. Build a controlled site fixture with pagination, expired login/MFA, layout changes and known side effects.
3. Exercise real browser interaction, actual extracted values and sanitized evidence; defer personal sessions to F16 after F20/F21.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F14.C01 | Real browser extracts current controlled/public data and handles pagination/layout failure honestly. | browser |
| F14.C02 | Login/MFA/expired-session handoff and resume are visible; cookie/state material stays with provider. | browser |
| F14.C03 | Unknown writing/autosave operations cannot use the read path; unsupported sites request handoff. | integration |

**Scope boundary:** Browser mocks do not qualify this. Do not expose unrestricted evaluate/click operations that bypass effect policy.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F14`. Required pending checks block completion.

## F15 — Effects and reconciliation

**Completion prerequisites:** F12, F13, F14.
**Owned areas:** services/core/alpha/capabilities; apps/desktop/src; workers/browser; tests/browser; tests/integration.
**Read:** specifications/Current Release Specification.md#7; specifications/contracts/Capability Protocol.md; product/Current Release UX Specification.md#7.

**Implement in this order:**

1. Implement durable intent, exact approval binding, current rechecks, provider dispatch and meaningful receipts.
2. Add controlled-site form fill/review/submit and provider idempotency/reconciliation paths.
3. Inject timeout/kill after dispatch, altered payload, cancellation and revoked authority.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F15.C01 | Controlled form uses supplied facts, requests missing facts, reviews actual values and submits once. | browser |
| F15.C02 | Changed account/destination/payload/expiry invalidates stale approval. | integration |
| F15.C03 | After-send uncertainty is reconciled without blind retry; cancellation does not claim reversal. | integration |

**Scope boundary:** Controlled submission is not live third-party submission. Avoid claiming HTTP success alone confirms a business effect.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F15`. Required pending checks block completion.

## F16 — Real generated job workflow

**Completion prerequisites:** F10, F13, F14, F15, F20, F21.
**Owned areas:** evals; tests/browser; docs/development/evidence.
**Read:** delivery/Prototype_Scope_and_Acceptance.md#F16; delivery/Prototype_Scope_and_Acceptance.md#6; product/Current Release UX Specification.md#6.

**Implement in this order:**

1. Run an ordinary user job request through Alpha; let the user clarify preferences, supported sources and selected profile facts.
2. Verify fresh collection/deduplication, useful views, match explanations and preserved user statuses after refresh.
3. Fill a permitted real form with takeover/review; retain controlled receipt evidence and only submit live if specifically authorized.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F16.C01 | Real qualified source data is gathered by the generated workflow with no job-specific Core edits. | live_source |
| F16.C02 | The resulting review/tracking UI is useful and retains user changes after refresh. | rendered_ui |
| F16.C03 | A permitted real form is filled from confirmed facts and handed off/reviewed; submission claims exactly match evidence. | live_source |

**Scope boundary:** If a platform defect is fixed, record a new evaluation cohort. No invented personal claims or universal-board promise.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F16`. Required pending checks block completion.

## F17 — Local schedules

**Completion prerequisites:** F12, F15.
**Owned areas:** services/core/alpha/schedules; apps/desktop; packages/contracts; tests/integration.
**Read:** specifications/Current Release Specification.md#9; architecture/Deployment and Execution Architecture.md; product/Current Release UX Specification.md#9.

**Implement in this order:**

1. Implement daily/weekly/interval triggers, timezone policy, unique occurrence keys and overlap limits.
2. Dispatch through the existing action path; support pause/edit and manual retrigger linked to missed occurrences.
3. Test deterministic clock edges and actual Mac close/quit/sleep/wake behavior.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F17.C01 | Repeated scans and edited triggers cannot dispatch duplicate/obsolete occurrences; overlap is recorded. | integration |
| F17.C02 | DST/timezone and interval behavior matches the explicit policy. | integration |
| F17.C03 | Window close preserves execution; quit/sleep missed work is visible and never automatically replayed. | native |

**Scope boundary:** No cloud/always-on claim and no bespoke scheduler execution path that bypasses action policy.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F17`. Required pending checks block completion.

## F18 — Evidence-based repair

**Completion prerequisites:** F10, F12, F14, F17.
**Owned areas:** services/core/alpha/assistant; services/core/alpha/builds; apps/desktop/src; evals.
**Read:** product/Current Release UX Specification.md#8; architecture/Input Memory and Procedure Architecture.md; specifications/Current Release Specification.md#4.

**Implement in this order:**

1. Create scoped diagnostic context from the failing run/source/current brief with redaction and limits.
2. Route reconnect/settings/reconciliation/code problems to their correct mechanisms; generate code fixes in a candidate.
3. Reproduce a broken source, repair within limits and rerun unaffected journeys and data-preservation checks.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F18.C01 | Real generation repairs an induced source failure and preserves user decisions after regression tests. | live_model |
| F18.C02 | Reconnection/configuration/unknown-effect problems are not misrouted to blind rebuild or retry. | integration |
| F18.C03 | Failed repair stops within limits and leaves the existing release/data available. | integration |

**Scope boundary:** An explanation or manual developer edit is not an AI repair. Do not widen authority to make a repair pass.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F18`. Required pending checks block completion.

## F19 — Frozen-platform breadth evaluation

**Completion prerequisites:** F08, F11, F16, F17, F18.
**Owned areas:** evals; docs/development/evidence.
**Read:** delivery/Prototype_Scope_and_Acceptance.md#F19; delivery/Prototype_Scope_and_Acceptance.md#6; delivery/Prototype_Scope_and_Acceptance.md#7.

**Implement in this order:**

1. Freeze platform commit, select the held-out family and preserve original prompts and user clarification.
2. Execute six reusable attempts, two one-off attempts and two change/repair attempts with full attempt/usage records.
3. Score independent outcomes/UX and report first-pass versus eventual results against G4.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F19.C01 | At least 5/6 reusable attempts succeed within repair limits and each of three families has a success. | evaluation |
| F19.C02 | Both one-off and both change/repair requests meet their respective output/data rules. | evaluation |
| F19.C03 | No unauthorized behavior or false success occurs; all failed attempts and platform changes are visible. | review |

**Scope boundary:** Do not select only successful attempts or treat this small sample as a population reliability estimate.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F19`. Required pending checks block completion.

## F20 — Execution boundary qualification

**Completion prerequisites:** F03, F07, F12, F14, F15.
**Owned areas:** apps/desktop/src-tauri; workers; services/core/alpha/capabilities; tests/qualification.
**Read:** architecture/Security Privacy and Data Boundaries.md; architecture/Deployment and Execution Architecture.md; specifications/contracts/App UI Bridge.md; architecture/Implementation Blueprint.md#10.

**Implement in this order:**

1. Start hardening after F03, then qualify complete builder/App/parser/browser profiles after controlled providers exist.
2. Run hostile canary probes for home/data/secrets, traversal/symlinks, descriptors, sockets/local services, subprocesses and quotas.
3. Exercise UI/native/approval boundaries and fail closed when a profile cannot enforce the promised restrictions.
4. Probe writes/rename/replacement through shared installations, package-store hardlinks/symlinks, import/bytecode/library caches and another worker scratch path. Prove actual OS denial rather than assuming cache reuse or chmod enforces isolation.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F20.C01 | Actual supported-Mac hostile probes cannot read unrelated data/secrets or bypass broker network/authority. | native |
| F20.C02 | Descendant cleanup, quotas and revocation work without a silent weaker mode. | native |
| F20.C03 | Failed candidate profile has an explicit qualified local replacement/reduced scope before any real-account use. | review |
| F20.C04 | Hostile App and builder processes cannot poison shared installed artifacts/caches or another worker’s scratch through direct paths, links, rename or import side effects. The actual supported-Mac restriction and surviving-profile integrity are recorded. | native |

**Scope boundary:** Separate directories, fake denied tools or upstream claims do not establish containment. No implicit remote sandbox.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F20`. Required pending checks block completion.

## F21 — Privacy, export and restore

**Completion prerequisites:** F09, F10, F12, F20.
**Owned areas:** services/core/alpha/data; services/core/alpha/artifacts; services/core/alpha/connections; apps/desktop; tests/integration.
**Read:** architecture/Security Privacy and Data Boundaries.md#6; architecture/Domain and Persistence Model.md; product/Current Release UX Specification.md.

**Implement in this order:**

1. Implement private storage/Keychain integration, encrypted-OS-storage setup checks and clear remote-inference disclosure.
2. Implement scoped retention, export/delete and consistent backup with protected secret handling.
3. Restore under concurrent-write/interruption scenarios; validate hashes/compatibility and restore schedules paused.
4. Include exact profile manifests/locks and needed distributable artifacts or a verified offline restore source in backup. Restore on a clean offline fixture; never re-resolve a missing profile to a newer version.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F21.C01 | Consistent restore recovers the intended records/versions and paused schedules; no unencrypted secret export. | integration |
| F21.C02 | Actual Mac credential/storage behavior and setup limits are tested and honestly described. | native |
| F21.C03 | Deletion/retention removes the intended scope while preserving unrelated files and unresolved-effect evidence policy. | integration |
| F21.C04 | A clean offline restore reuses the exact retained dependency identities and data. A deliberately missing artifact yields a precise blocked repair state, with no floating-version fallback or silent change to executable behavior. | integration |

**Scope boundary:** Do not claim an independent encrypted app vault or assume exported files inherit disk protection elsewhere.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F21`. Required pending checks block completion.

## F22 — Mac packaging and update

**Completion prerequisites:** F01, F14, F20, F21.
**Owned areas:** apps/desktop/src-tauri; packaging; CI/release configuration; tests/qualification.
**Read:** architecture/Deployment and Execution Architecture.md; architecture/Implementation Blueprint.md#1; delivery/Prototype_Scope_and_Acceptance.md#F22; architecture/Implementation Blueprint.md#10.

**Implement in this order:**

1. Package/provision pinned runtimes, browser and builder dependencies and record redistribution/license decisions.
2. Implement signed/notarized install/update, compatibility/migration and failure recovery on clean supported Macs.
3. Qualify the second desired BYOK provider and complete end-user setup without developer tooling.
4. Qualify managed profile provisioning once per identity, interrupted install reconciliation and reference/lease-aware cleanup. Preserve active/candidate/running/rollback references and perform package-cache pruning only through supported tooling.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F22.C01 | A clean supported Mac installs and creates/uses a result with no terminal or user Python requirement. | native |
| F22.C02 | Corrupt/interrupted update and old stores recover without losing working data. | native |
| F22.C03 | Both advertised model providers pass real route tests and signed binary/environment evidence is retained. | live_model |
| F22.C04 | Clean-Mac concurrent requests converge on one sealed profile; interrupted installs never become ready. Cleanup cannot delete a profile referenced by a Version or live lease, including a racing acquisition, and unreferenced cleanup recovers after restart. App launch performs no install/sync. | native |

**Scope boundary:** Missing signing credentials/hardware is a pending gate; a dev launch is not installer qualification.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F22`. Required pending checks block completion.

## F23 — Nontechnical usability pilot

**Completion prerequisites:** F19, F22.
**Owned areas:** evals; docs/development/evidence; UI areas directly implicated by findings.
**Read:** product/Current Release UX Specification.md#10; delivery/Prototype_Scope_and_Acceptance.md#F23.

**Implement in this order:**

1. Prepare a five-participant protocol with create/use/change/recover tasks inside the supported envelope.
2. Observe real participants with informed account handling; record every intervention and misunderstanding.
3. Fix material UX defects, rerun affected journeys and report actual sample size/outcomes.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F23.C01 | Five intended users have actual recorded create/use/change/recover evidence. | user_study |
| F23.C02 | At least four complete without technical intervention and no participant is misled about effects. | user_study |
| F23.C03 | Failures, assistance and fixes are retained with anonymized evidence. | review |

**Scope boundary:** An AI simulation is not a participant. A smaller sample leaves the full gate pending.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F23`. Required pending checks block completion.

## F24 — Private-alpha evidence and decision

**Completion prerequisites:** F19, F20, F21, F22, F23.
**Owned areas:** docs/development/evidence; release notes; support/onboarding documentation.
**Read:** delivery/Prototype_Scope_and_Acceptance.md#F24; delivery/Delivery Checklist.md; architecture/Security Privacy and Data Boundaries.md.

**Implement in this order:**

1. Audit exact artifact/profile identities, completion evidence and all G0–G5 requirements.
2. Run only relevant final regression and package the concrete candidate, limitations, measured quality/cost and recovery instructions.
3. Present release readiness separately from permission to distribute; carry out distribution only within actual authorization.

**Required checks:**

| ID | Expected result | Evidence |
|---|---|---|
| F24.C01 | All prerequisite gates have matching evidence and no blocking safety/data/usefulness failure is hidden. | review |
| F24.C02 | Candidate hashes, supported profiles, limitations, pilot results and rollback procedure are complete. | review |
| F24.C03 | Relevant final regression passes on the candidate being assessed, with actual environments recorded. | integration |

**Scope boundary:** Documentation readiness is not product readiness. Do not publish simply because the checklist is populated.

**Deliver:** reviewable implementation, actual checks and evidence, updated local state, and next eligible task or the M1 review packet. Verification command: `just verify-ticket F24`. Required pending checks block completion.
