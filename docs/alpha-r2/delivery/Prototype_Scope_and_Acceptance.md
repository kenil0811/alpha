# Alpha — from-scratch implementation plan

**Baseline R2 · 24 September 2026 · Implementation pending.** This document owns work order, dependencies, acceptance scenarios and milestone gates. Handoff revision 3 (25 September 2026) sets the initial engagement to F01–F08 and defines shared dependency maintenance. No previous implementation is required.

## 1. The product and the test of success

Alpha lets a nontechnical person describe work they want handled, answer useful setup questions and receive a usable result that Alpha can operate and change. Results include an answer, one-off action, file, background workflow, personal interface or combination. **The platform team builds the system; end users create their own solutions through it.**

The loop is understand → select context/access → choose the result → create or configure → execute and inspect → deliver → operate → change or repair. AI handles solution design and implementation. The platform owns permissions, persistence, execution, verification and presentation standards. Users own goals, corrections, access and consequential choices.

The calorie tracker and job workflow are acceptance scenarios, never platform features. We do not add calorie/job tables, routes, screens or domain branches to Core. An unfamiliar workflow within available capabilities must be possible without changing platform source code. Reusable connectors and interaction patterns are allowed; a fixed catalogue of complete apps is insufficient.

A successful release lets users create, use, change and recover their work without a terminal, database designer or workflow-node editor. The result does real work; a dashboard without functioning actions or trustworthy data fails. Imperfect extraction, incomplete site coverage and visible repairable failures are acceptable. Silent data loss, fabricated completion and uncontrolled actions are not an acceptable interpretation of “80%.”

## 2. Scope and release boundaries

| Boundary | Included | Deferred beyond this boundary |
|---|---|---|
| M1 internal creation proof | Conversation, safe selected inputs, real builder, generated Python logic and optional React UI, records, model calls, preview, execution, reopen | Real accounts, external writes, user distribution |
| M2 maintainable local proof | Data-preserving change, candidate validation, rollback, one-off outputs, interruption recovery | Broad integrations |
| M3 external-work proof | HTTP, dedicated browser sessions, login handoff, supported form filling, reviewed submission and receipts | Universal site coverage |
| M4 complete functional alpha | Local schedules, runtime reasoning, generated repair, unfamiliar requests and multiple output forms | Cloud execution and general computer control |
| M5 private alpha | Qualified containment, storage/credential protection, backup/restore, signed Mac installation, nontechnical usability | Public-scale hosting, teams, marketplace and billing |

Mac first, with Apple Silicon as the first native qualification target. Record the supported macOS range after F01/F22 testing. Windows, always-available deployment, voice/screen context and broader desktop capabilities remain future extensions. They must not require making every result into an App.

## 3. Decisions that determine the build

1. A **Task** is one-off work; an **App** is reusable work. A background workflow is an App without custom UI. “Workflow” and “automation” may be user-facing names, not extra lifecycle engines.
2. Invoke existing capabilities directly when sufficient; generate code when it adds useful behavior. No mandatory graph editor or UI description language.
3. Platform records, artifacts, actions, files, browser, HTTP and model providers support generated schemas, rules and interfaces.
4. Assistant, UI and schedules invoke the same declared actions. Validate real callable bindings rather than assuming an action ID identifies working code.
5. User data lives outside immutable code versions. Candidate validation precedes live activation or migration. Code rollback does not roll back data.
6. Functional and visual verification are part of building. Compiler success and screenshots alone do not establish usefulness.
7. Qualify OpenCode first behind a small BuilderHarness interface. Claude Agent SDK is the fallback candidate if a recorded blocker prevents qualification. Two full adapters are not a prerequisite for product learning.
8. Use Tauri/Rust, React/TypeScript, a modular Python Core with separate workers, and SQLite. No previous codebase is required.
9. Share platform services, maintained SDK/UI/module packages and immutable dependency profiles. Keep writable data, credentials and worker authority isolated. Implementation Blueprint section 10 defines installation, pins, upgrades and cleanup; do not invent a registry service, per-App environment installer or runtime plugin marketplace.

See the architecture and release specification for ownership and field-level contracts. This document owns sequencing rather than duplicating those definitions.

## 4. Milestones and effort assumptions

Estimates assume one full-time experienced engineer using AI coding assistance, a development Mac and frequent short founder reviews. They are not commitments. A second engineer can overlap independent UI/runtime tickets once shared interfaces stabilize; elapsed time will not halve automatically.

| Milestone | Tickets | Indicative engineering days | Exit evidence |
|---|---|---:|---|
| M0 technical qualification | F01–F03 | 3–5 | Real harness run, process cleanup, UI boundary and sandbox feasibility |
| M1 user-driven creation | F04–F08 | 10–15 | Ordinary request → generated result → use → reopen, across different requests |
| M2 maintainability | F09–F12 | 7–10 | Safe concurrent changes, versions, Task output and recovery |
| M3 external work | F13–F16 | 10–15 | Fresh reads, browser handoff, reviewed supported form action |
| M4 recurrence and repair | F17–F19 | 7–10 | Scheduling, generated repair and frozen-platform breadth evaluation |
| M5 private-user readiness | F20–F24 | 10–15 | Execution boundary, signed delivery, restore and usability evidence |

Initial hypothesis: **47–70 engineering days, approximately 10–14 working weeks**, plus 2–4 weeks contingency for packaging, site behavior or quality. F20/F21 work starts earlier where real account tests depend on it; the table groups outcomes, not permission to delay prerequisites. Re-estimate after M1 from actual success, latency, cost and rework.

**Initial execution scope: F01–F08 only.** Work autonomously within that set; stop at M1 and present the working G1 creation experience, all required evidence, measured cost/latency, failures and exact launch instructions. Do not implement later ready tickets, including F11, before this review. Later milestones are specified for continuity, not silently authorized. If ordinary requests produce poor results, repair creation/verification inside M1 before expanding capabilities. The playbook and helper record a subsequent explicit user scope extension; selecting M3 or M4 includes F20/F21 prerequisites.

**G0 / M0 exit:** F01's actual Mac lifecycle, F02's real generated candidate and F03's UI/isolation feasibility evidence are recorded. This permits the internal nonsensitive M1 proof, not personal-account use or distribution.

Recommended execution order for one engineer: F01 → F02/F03 → F04–F08 → F09–F12 → F13–F15 using controlled/nonsensitive sources → F20/F21 → F16–F19 → F22–F24. Start F20's hardening as soon as F03 exposes gaps. F13–F15 establish provider behavior before its final protection tests; F16 supplies real-account qualification after protection. The numbering groups capabilities and release work, not a strict numeric queue.

## 5. Implementation tickets

Every ticket ends with a reviewable diff, exact commands, applicable acceptance IDs, retained evidence and the next ready task. Missing native hardware or credentials means a gate is pending. A mock is useful for controls but cannot satisfy a live/native claim. Paths refer to the proposed clean repository in Implementation Blueprint; create directories only when exercised.

### F01 — boot a minimal desktop-to-worker path

**Dependencies:** none. **Owners:** `apps/desktop`, `services/core`, `packages/contracts`, integration tests and toolchain.

Build the shell frame with one request input/result area and final typography/spacing tokens. Start Python Core from Tauri, authenticate shell IPC, start a supervised synthetic worker, persist a run in SQLite and stream its status. This fixture proves transport, not app generation. Add exercised commands: `just dev`, `just check`, `just test-core`, `just test-ui`, `just test-integration`.

**Acceptance:** fresh checkout starts; bundled Python does not depend on user Python; closing/reopening the window preserves runtime/results; explicit quit terminates descendants; invalid IPC credentials fail; worker failure displays a failed run; restart reopens durable state. Record exact toolchain and Mac versions. Do not build empty future navigation.

### F02 — qualify the real builder and model route

**Dependencies:** F01. **Owners:** Core builds/models, builder worker, qualification tests.

Integrate OpenCode headless behind `start/events/cancel/result`. Use private per-build configuration/workspace, loopback authentication and explicit command/network profiles; disable ambient projects, plugins, sharing and production sessions. Implement the platform model gateway and one BYOK route. Give children scoped temporary gateway credentials, not durable provider keys. Record route, usage, budgets and dependency pins.

Generate a small pure transformation package from a plain goal, compile it and execute its actual declared function. This qualifies real generation before the record service arrives in F05. Exercise real failure, cancellation with descendants, event normalization and cleanup. A provider's final prose is not proof of a runnable package.

**Acceptance:** real generated source runs; failures classify correctly; cancel cleans up; no secrets enter source/logs; usage is recorded or explicitly unavailable; restart cannot silently resume an obsolete build. Timebox the first adapter qualification to two working days. If blocked by a reproducible issue, record it and qualify Claude Agent SDK through the same interface. No paid run begins without a supplied route and explicit budget.

### F03 — prove UI isolation and local containment feasibility

**Dependencies:** F01; synthetic workers may stand in while F02 completes. **Owners:** desktop, UI bridge, worker profiles, qualification tests.

Render arbitrary generated React in an unprivileged surface. Prove it cannot invoke native commands, read shell tokens, navigate the trusted shell or call another App. Evaluate a pinned sandbox-runtime profile against credential-file reads, symlink escape, subprocess escape, sockets, localhost and cleanup. Separate folders and upstream default settings are not containment.

**Acceptance:** bridge enforcement is demonstrated; packaging limits and failed probes are recorded; each remaining isolation failure has an F20 release-blocking test. M1 may continue with nonsensitive fixtures under the internal profile. Before real personal/account data, qualify the boundary or choose a local VM/narrower profile. Do not silently substitute cloud execution.

### F04 — derive a solution brief from the user's request

**Dependencies:** F02. **Owners:** assistant, contracts, conversation/result surfaces.

Route to answer, Task or App. Ask material questions; use deliberately selected context; create a versioned SolutionBrief containing outcome, primary interaction, inputs, user decisions, data, actions, result surfaces, recurrence, constraints, acceptance examples, assumptions and unavailable capabilities. Show a short plain-language interpretation. Reuse existing applicable grants/preferences.

**Acceptance:** a tracker request is clarified without asking users to design a database; a one-off request creates no App; missing access is specific; corrections revise the brief; safe reversible defaults allow progress. Aim for 1–3 short question rounds for simple requests, without guessing material facts to hit that target.

### F05 — provide records, artifacts and runtime model access

**Dependencies:** F01/F02/F04. **Owners:** Core data/artifacts/models and Python App SDK.

Implement generated collection schemas, validated CRUD, stable IDs, ownership, typed filtering/sorting, pagination and count/sum/group aggregation. Initial field types: strings, numbers, booleans, dates/times, enums, references and bounded JSON. Add artifact handles and bounded structured model calls with provenance. Generated functions use `ctx.records`, `ctx.artifacts`, `ctx.models`; never raw database paths or durable keys.

**Acceptance:** generated records validate, query, aggregate and persist after restart; cross-App access fails; local transaction errors roll back. Model-derived estimates are labeled and correctable. F09 supplies real concurrency/idempotency proof before multiwriter reliance. Do not build a separate financial or nutrition subsystem.

Shared maintenance acceptance for F05: create the first immutable managed Python runtime profile and SDK package. Two fixture Apps reuse its exact installation in separate workers while their scratch, records and broker authority remain distinct. Inventory and pin the profile; this functional check does not certify F20 containment.

### F06 — build the shared design and interaction kit

**Dependencies:** F03/F04. **Owners:** UI kit/bridge, app template, UI tests.

Provide page frame, quick entry, form controls, record list/table, filter bar, detail drawer, metric/trend view, review queue and empty/loading/error/operation states. Include keyboard behavior, accessible labels, tokens, composition examples and a reference sheet available to the builder. Use Radix, Tailwind and TanStack components selectively. Custom React composition remains possible; tables are an option, not a universal UI.

**Acceptance:** enter/correct a record, filter a list and recover from a failed save by keyboard; no blocking overflow at supported widths; long labels, empty data and populated data work. References contain interaction patterns, not job/calorie domain logic.

Shared maintenance acceptance for F06: publish one maintained UI-kit/bridge package into the supported build profile. Two neutral fixture compositions import the same exact package; templates do not copy its implementation. Compiled output may contain bundled copies of the code. Version changes require rebuilding candidates.

### F07 — build, validate and repair a candidate

**Dependencies:** F02/F05/F06. **Owners:** build orchestration, validator worker, templates and evaluation helpers.

Generate in a candidate workspace. Check package paths, dependencies, schemas, actual handler bindings and UI compilation. Execute behavior against independent fixtures. Launch the candidate and exercise its primary interaction with empty, populated and error states. Give concrete failures to the builder for at most two automatic repair attempts; enforce deadlines and budgets outside the model. Keep candidate-authored tests as supplementary evidence.

**Acceptance:** missing handler, fake persistence, broken primary action and blocking overflow are rejected. A failed builder result stays failed even if some checks pass. Repair stops at its limit. Preview cannot be mistaken for an activated working release. Validation invokes actual generated functions, not ID-based surrogate handlers.

Shared maintenance acceptance for F07: seal exact SDK/module/runtime/UI profile digests, reject incompatible or undeclared dependency resolution and prevent runtime installation. A candidate must use the same profile in validation and execution; extra dependencies follow the managed qualification path.

### F08 — deliver, use and reopen a generated solution

**Dependencies:** F04–F07. **Owners:** assistant orchestration, release activation and shell result/Apps surfaces.

Connect request → clarification → real build → validation → preview/result → activation. Show useful progress, required access and limits in user language. Retain brief, code version, release and records separately. Support a reusable action without a custom interface as well as a generated interactive tool.

**G1 / M1 exit:** produce a calorie tracker, a different collection/review outcome and a third request chosen after freezing platform code. At least one output has no custom dashboard. No founder source edits between request and success. Retain prompts, questions, candidate hashes, behavior results, UI evidence when applicable, reopen proof, cost and limitations. Handwritten exemplar products cannot satisfy this gate.

Additional G1 evidence: at least two actually generated results reuse the same managed runtime/SDK profile with separate records and writable scratch; cancellation/failure of one preserves the other. Deliver this evidence at the M1 stop alongside the UX results. Do not substitute hand-authored fixtures for the G1 generated outputs.

### F09 — protect user changes and source ingestion

**Dependencies:** F05/F08. **Owners:** record service/SDK and integration tests.

Use compare-and-swap SQL updates (`WHERE id = ? AND revision = ?`), affected-row checks and transactions. Add App/collection-scoped uniqueness and idempotency keys, batch writes, provenance and separation of source-owned fields from user decisions. Refresh must preserve notes, overrides and statuses. Return actionable conflicts.

**Acceptance:** two actual SQLite writers on the same revision produce one commit and one conflict; duplicate ingestion yields one item; refresh preserves corrections; retrying a local action with its key does not duplicate data. Repository mocks alone do not establish this.

### F10 — change behavior without losing data

**Dependencies:** F07–F09. **Owners:** versions/releases, migration runner and change review.

Separate settings changes from code changes. Build against candidate data copies. Diff schemas; allow additive compatible migrations first. Destructive/semantic migrations need preview, backup, explicit review and a tested restore path; arbitrary generated SQL migration is outside the initial profile. Existing runs pin versions; release activation and migrations use fencing against concurrent changes.

**Acceptance:** a generated new field/view preserves existing records; a bad candidate leaves the working release intact; competing builds cannot overwrite a newer activation; incompatible rollback is refused. Data restore warns about losing newer records; code rollback never implies data rollback.

Shared maintenance acceptance for F10: inventory every affected Version after a common module/SDK/UI update. Build separate candidates for two consuming Apps, deliberately fail one, activate only the compatible passing candidate, preserve both datasets and pin existing runs/rollback versions. A shared service patch is centrally applied only after compatibility checks; breaking service changes retain compatibility or identify and pause affected consumers, never silently run them against a changed contract.

### F11 — support one-off outputs and actions

**Dependencies:** F04/F05/F07. **Owners:** Tasks, parser helper, artifacts/viewer/export.

Implement Task revisions/attempts through the shared execution envelope and broker, without forged App IDs. Start with selected text/CSV and one qualified document format; isolate complex parsers. Deliver a report or transformed artifact with provenance. Ephemeral generated computation may use the worker boundary without creating a persistent App.

**Acceptance:** a document request delivers a file, not an unwanted dashboard; invalid inputs and cancellation are clear; retries preserve attempt history; path/archive escape fails. Audio output waits for a qualified synthesis provider; unsupported capabilities cannot be claimed as delivered.

### F12 — survive interruptions

**Dependencies:** F08–F11. **Owners:** run coordinator, leases, event store and Activity.

Persist state, checkpoints at actual durability boundaries, events, worker leases and cancellation. Reconcile abandoned runs after restart. Preserve committed outputs. Release idle workers during long user waits. Do not attempt transparent serialization of arbitrary Python stacks; re-entry uses durable step keys.

**G2 / M2 exit:** force kill Core/workers, restart and recover saved data plus meaningful interrupted state. Resume supported checkpoints without duplicate committed local work. Waiting work remains visible. F15 extends this evidence to external actions.

### F13 — connect HTTP sources and selected files

**Dependencies:** F09/F11/F12; personal/account data additionally requires F20/F21. **Owners:** broker, HTTP/file providers and Connections.

Implement bounded HTTP reads and named action profiles, redirect/destination checks, response limits, provenance and error taxonomy. Resolve selected files/folders through opaque handles. Keep Connection metadata separate from Keychain secrets. Qualify one public source and a controlled credentialed API with synthetic tokens/data; qualify personal-account access after F20/F21. Unknown APIs can be composed through qualified capabilities; they do not each need a business-specific platform module.

**Acceptance:** generated code retrieves fresh data, deduplicates and reports source/last checked; revocation blocks new requests; unapproved/private-network redirects fail; no credentials reach generated code. HTTP writes stay disabled until F15.

### F14 — use a dedicated browser session

**Dependencies:** F03/F12/F13. **Owners:** browser provider, visible handoff and integration tests.

Use managed Playwright contexts, login/takeover, navigation, inspection/extraction, screenshots and selected uploads/downloads. First test a controlled site with pagination, changed selectors, expired login and MFA; then qualify real sources. Prefer semantic locators and actual value inspection. Cookies and storage state remain with the provider. Arbitrary page JavaScript cannot become a general authority bypass.

**Acceptance:** connect, read a permitted page and recover an expired session. Actions that might write or autosave are gated by F15. Unsupported forms/CAPTCHA request handoff. Login supplies authentication, not blanket action permission.

### F15 — authorize effects and reconcile unknown outcomes

**Dependencies:** F12–F14. **Owners:** effect ledger, policy, approvals and provider receipts.

Persist intent before dispatch. Bind approval to exact account, destination, payload digest, run/release and expiry. Track prepared, awaiting approval, dispatching, confirmed, failed-before-effect and outcome-unknown. Use provider idempotency where available; otherwise inspect external state before retrying. Final submission presents trusted review of what will be sent. Reusable approval may cover a bounded supported operation family; do not repeatedly ask within already-authorized scope.

**Acceptance:** fill/review/submit a controlled form once; request missing facts; invalidate approval after payload changes; kill-after-send produces outcome-unknown until reconciled. Cancel does not undo a completed action. Generic HTTP/browser methods cannot bypass review by labeling writes as reads.

### F16 — qualify the generated job workflow

**Dependencies:** F10/F13–F15; real accounts require F20/F21. **Owners:** evaluation fixtures/evidence, with no job-specific Core code.

Start from an ordinary job request. Alpha clarifies preferences, generates collection/matching logic, creates useful review/tracking views and fills a supported application from confirmed facts. Distinguish discovered, shortlisted, preparing, submitted and unknown. Refresh preserves user decisions. Controlled forms provide repeatable submission tests; a tester must separately supply an authorized real application for live submission.

**G3 / M3 exit:** demonstrate fresh live source data and real form filling with review/handoff. Controlled receipt tests establish submission mechanics; any permitted live submission establishes only that path. A dry run is never a real submission, nor a few sources universal coverage. A one-off application Task uses the same capabilities without creating an App.

### F17 — schedule continuing local work

**Dependencies:** F12/F15. **Owners:** schedules/occurrences, tray/runtime state and automation controls.

Implement manual, interval and daily/weekly wall-clock triggers with IANA timezones. Use unique trigger/time occurrence keys and one active run per trigger initially. Mark overlap explicitly. Window close keeps runtime alive; quit, sleep and device unavailability produce visible missed occurrences. Relaunch never automatically catches up. Manual retrigger creates a new linked run.

**Acceptance:** deterministic clock and real Mac sleep/wake tests; DST behavior matches the specification; duplicate scans cannot duplicate work; edits fence obsolete triggers; pause works; missed work stays visible. Runtime availability is explicit in UI.

### F18 — diagnose and repair using evidence

**Dependencies:** F10/F12/F14/F17. **Owners:** diagnostic context, repair orchestration and change/settings UX.

Use scoped errors, sanitized source snapshots/screenshots and the current brief. Route expired access to reconnect, settings changes to configuration, code failures to candidate generation and unknown effects to reconciliation. Reproduce the failure, test the repair and rerun unaffected main journeys. Preserve the working release. Renew review only for expanded authority or material behavior changes.

**Acceptance:** a changed source breaks a generated workflow; “fix this” produces and validates a repair; unsuccessful attempts stop at budget; data and user decisions survive. No source-specific repair branch enters Core. Explanations without changed/verified behavior do not count.

### F19 — prove breadth and measure quality

**Dependencies:** F08/F11/F16–F18. **Owners:** evaluations and retained scorecards.

Freeze the platform commit. Run three reusable request families with two ordinary-language variants each, two one-off requests and two change/repair requests. One family is held out until evaluation. Users may clarify/grant access; developers may not edit generated source or Core between prompt and result. A platform fix starts a new scored cohort; retain previous failures.

**G4 / M4 exit:** at least 5/6 reusable attempts succeed after at most two automatic repairs each, and every family has a success. Both one-off requests deliver without unwanted Apps. Both change/repair tasks preserve data and pass behavior checks. Every attempt respects authority and reports outcome honestly. Keep first-pass and eventual success separate. This sample is a release gate, not a statistical reliability claim.

### F20 — qualify generated-code execution

**Dependencies:** F03/F07/F12 to start; F14/F15's controlled-provider behavior for final qualification. Finish before F16 real-account testing. **Owners:** sandbox providers, host control and adversarial tests.

Harden separate builder, parser, App worker and browser profiles. App workers use broker-only network and no ambient home/database/session access. Builders use approved dependency/model routes without production sessions. Probe symlinks, archives, sockets, inherited descriptors, subprocesses, quotas and cleanup on supported Macs. Test UI/native boundary and approval spoofing.

**Acceptance:** actual hostile probes cannot read unrelated files/secrets or bypass broker authority; descendant cleanup and limits work; no silent weaker fallback. If the local profile fails, external release remains blocked until a qualified local alternative or explicit capability reduction exists. A separate directory is not the alternative.

Shared maintenance acceptance for F20: hostile builder/App probes cannot write, replace, rename or poison shared dependency artifacts, links, bytecode caches or another worker’s scratch. Reuse of a cache/hardlink is not isolation; qualify the real OS enforcement, not just file mode bits.

### F21 — protect personal data and verify restore

**Dependencies:** F09/F10/F12/F20. **Owners:** storage/secrets, export/delete/restore and privacy UX.

Use Keychain, a private data directory, explicit model/data disclosure, retention controls and consistent backup/restore. The initial private-alpha at-rest profile requires OS-backed encrypted storage (FileVault or a qualified encrypted volume), checked and explained during setup. It protects a powered-off device, not another process under the unlocked user. Do not advertise a separately encrypted app vault. Exported copies/backups have their own storage/encryption choice. Bound screenshot retention and redact logs.

**Acceptance:** restore returns records, compatible versions and paused schedules; secrets are securely reattached when needed; deletion removes scoped data/evidence without unrelated files; backup consistency under writes is demonstrated. “Local” clearly does not mean “no remote inference.”

Shared maintenance acceptance for F21: backups retain exact profile manifests/locks and the required distributable artifacts or a verified offline restore source. A clean offline restore must never silently resolve newer dependencies; report a genuinely unavailable profile and keep affected execution blocked.

### F22 — install and update on a clean Mac

**Dependencies:** F01/F14/F20/F21. **Owners:** native packaging and release scripts.

Bundle/provision pinned Python, browser and builder dependencies without a terminal; verify licensing/redistribution. Sign/notarize; test clean install, first launch, upgrade, failed update and uninstall. Preserve data and runtime compatibility with recoverable migrations. Qualify the second desired BYOK model provider before claiming support.

**Acceptance:** tester installs, connects a provider, creates a result and performs a browser workflow without developer tooling. Corrupt/interrupted downloads and old stores recover clearly. Record binary hashes, supported OS versions and exact runtime profiles. Missing hardware/signing access remains a visible pending gate.

Shared maintenance acceptance for F22: provision profiles once per exact identity, start workers without package-manager mutation, survive interrupted installs, and retain profiles referenced by active/candidate/rollback Versions or live leases. Prove cleanup cannot delete a referenced profile and that the supported offline restore path works. Reuse uv/pnpm stores under trusted management; do not write a new dependency resolver.

### F23 — observe nontechnical use

**Dependencies:** F19/F22. **Owners:** research protocol, anonymized evidence and UX fixes.

Recruit five intended users when available. Each creates a small real workflow within supported capabilities, uses it, changes it and recovers from one failure. Observe without explaining. Count founder/developer help as intervention. Participants supply account access themselves.

**Acceptance:** at least four of five complete the use-and-change journey without technical intervention; remaining failures are understood; no user is misled about whether a consequential action happened. A smaller study is reported honestly and does not silently satisfy the five-person gate.

### F24 — assemble the release decision

**Dependencies:** F19–F23. **Owners:** evidence manifest, limitations and release/support notes.

Run relevant final regression/native gates. Assemble supported capability/OS/model/site profiles, open defects, success/cost/latency measures, authority/data tests, pilot outcomes and rollback procedure. A serious blocked gate cannot be averaged away by an overall score.

**G5 / M5 exit:** a concrete private-alpha candidate has all required evidence. Distribution is limited to the qualified audience/profile and existing authorization. This planning task does not authorize model spending, application submission, publication or deployment.

## 6. End-to-end acceptance scenarios

**A01 — personal tracker.** “Track what I eat and how much, with calories, history and trends.” Clarify serving ambiguity and desired summaries; targets are user supplied. Require fast entry, editable estimates, daily totals, history and a meaningful trend. Test three entries on different days, correction, deletion and reopen. Missing days are not fabricated zero intake. “Add protein” tests data-preserving change. Fail for generic empty forms, nonfunctional controls or totals inconsistent with saved entries. Domain rules belong in generated code or a chosen data provider.

**A02 — opportunity workflow.** “Find software developer jobs that fit me, track applications and help me apply.” Clarify preferences, available sources and profile facts. Retrieve/normalize/deduplicate, retain source/freshness, show useful match explanations, preserve user statuses/notes and fill a supported form. Ask for missing claims and distinguish prepared/submitted/unknown. Fail for seeded results described as fresh, overwritten user decisions, invented answers or duplicated submissions.

**A03 — background result.** An evaluation request such as checking approved pages and producing a change digest should yield a workflow with settings, schedule, history and output. A custom dashboard is optional. Change source data, run once, quit/sleep through another occurrence and inspect missed work. Manual retrigger is deliberate.

**A04 — one-off output/action.** Transform selected documents into a downloadable brief; separately fill a particular permitted form from selected facts. No hidden persistent App. Keep artifact provenance and the same action/receipt protections as reusable work. Explain missing audio/specialized capabilities precisely rather than claiming them.

**A05 — change and repair.** Request a new field/view/rule and introduce a source-layout failure. Include a bad candidate and a failed repair. Current data and last usable release survive. Expanded permissions are visible; uncertain external effects are reconciled, never replayed as a “fix.”

**A06 — unfamiliar request.** After freezing the platform, choose a different workflow within the supported envelope, e.g. research evidence review or household maintenance. Do not supply a developer-authored schema/UI. A truly missing shared capability is a recorded limitation; adding it changes the platform cohort and does not retroactively pass the original attempt.

## 7. Quality scorecard and defaults

| Dimension | Evidence and initial gate |
|---|---|
| Usefulness | Independent expected outputs plus completed primary user journey; no placeholder success |
| UX | Clear main action, editing and recovery; no blocking overflow or keyboard trap |
| Data | Persist/reopen, aggregation, conflict, refresh and migration checks; zero known silent loss |
| Authority | Actual denied operations, exact approval binding and revocation tests |
| Breadth | Frozen-platform G4 cohort including held-out family |
| Repair | Reproduced failure, candidate checks and unaffected-journey regression |
| Time to value | Initially target median under 5 minutes after setup for small local builds; measure before promising |
| Cost | Bounded calls/attempts, actual versus estimated usage clearly separated |
| Independence | Four of five nontechnical users complete without technical intervention |

Internal qualification defaults to implement: one builder at a time; at most two automatic repair attempts; 12 minutes per build attempt; 30 minutes total including repair; founder-configured monetary ceiling before live calls. These are initial policy settings, not permission to spend now. Runtime reads may retry twice with backoff within the deadline. External writes get no automatic retry without verified idempotency or reconciliation. Provider timeouts may still incur cost; record uncertainty.

Stop rules: if G1 fails, improve brief quality, kit use, model/harness choice or verification before expanding scope. If G3 fails, fix/narrow supported action profiles and disclose limits. If G5 fails, remain internal. Do not relabel a failure as a demo pass.

## 8. Highest-risk assumptions and responses

| Risk | Earliest evidence | Response if the assumption fails |
|---|---|---|
| Builder produces generic, unusable screens | G1 primary journeys and rendered review | Improve brief/kit examples/verification or qualify a better route; stop expanding scope |
| Code works only for memorized examples | G1 held-out request, then frozen G4 cohort | Remove domain shortcuts, inspect missing shared capabilities and rerun a new cohort |
| Harness/model proxy or bundled runtime is impractical | F01/F02 real packaged/adapter tests | Use the bounded fallback decision; change one evidenced dependency before broad implementation |
| Local restrictions cannot protect personal data | F03 probes and F20 hostile tests | Qualify a local replacement or explicit narrower profile; keep external release blocked |
| Websites resist reliable automation | F14 controlled failures and F16 real paths | Prefer supported APIs, narrow site profiles and preserve user takeover; make no universal claim |
| Build/repair cost or latency is too high | Complete G1/G4 usage and time distributions | Reduce context/rebuild scope, improve component reuse, tune route and enforce limits |
| Repair causes new failures or data loss | F09/F10/F18 regression and crash tests | Keep previous release, stop activation and improve migration/verification before retry |
| Users need coaching despite functional output | F23 observed interventions | Fix creation/journey UX and repeat the affected study task; do not add a tutorial to hide a broken flow |

Measure local creation funnel, number of clarification rounds, first-pass/repaired success, user edits, time-to-first-useful-action, cost per successful build/run and recurring completion/missed/failure counts. Start with local opt-in diagnostic export; do not add undisclosed remote telemetry. These measures decide the next capability investments.

## 9. What we deliberately do not build first

No visual workflow editor, fixed template catalogue, per-App server, arbitrary technology stack, plugin marketplace, team system, billing, Kafka/Redis, distributed workflow engine or mandatory multiagent hierarchy. No broad memory/continuous observation. No hand-built exemplar apps. No universal-table UI. No deferred “make it pretty later” phase.

## 10. How coding starts

Use START_HERE.md in the bundle, then F01 in Task_Packets.md. Inspect the authorized workspace and preserve unrelated work; no prior branch or migration is required. Implement F01, qualify F02/F03 and complete F04–F08. Stop at M1 for product review. All implementation starts pending; a plan does not establish completion.

For coding outside this project, give the agent Alpha_Agent_Context.zip and paste Agent_Start_Prompt.md. Task_Packets.md supplies ordered implementation steps and numbered checks for every ticket; TASKS.json supplies machine-readable dependencies and evidence categories. The included agent_handoff.py validates the snapshot and local progress records and identifies ready tickets. AI_Coding_Agent_Playbook.md defines autonomous continuation and when actual missing access/authority requires the founder. No chat history or live project access is needed.
