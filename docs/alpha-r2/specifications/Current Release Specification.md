# Current release specification

**Baseline R2 · contract version 0.2 · 24 September 2026.** Normative design for the clean-start Mac alpha. These contracts are to be implemented incrementally; they are not generated-schema or runtime conformance claims. Specifications Index defines authority. Shared dependency fields were clarified in handoff revision 3 (25 September 2026); no deployed implementation is claimed.

## 1. Contract conventions

Payloads use JSON-compatible values, opaque IDs and RFC3339 UTC timestamps. Store IANA timezones for wall-clock meaning. `contract_version` is exactly `0.2` for this profile. At trust boundaries reject unknown authority-bearing fields, invalid enum values and unexpected owner variants. User business records can have additional fields only when their declared collection schema permits them. Secrets, absolute device paths and ambient account authority are never portable payload fields.

Generate JSON Schema and TypeScript types from the Python contract source in `packages/contracts` as each ticket lands. Check generated outputs for drift in CI. Keep hand-authored expected fixtures for important negative cases. Future compatible additions must have an explicit version policy; do not silently accept unknown capabilities or permissions.

## 2. SolutionBrief

All listed top-level fields are required unless marked optional. Empty arrays mean deliberately none, not an unasked/unknown answer; unresolved material choices belong in questions/assumptions.

| Field | Type / meaning |
|---|---|
| `id`, `revision`, `conversation_id`, `created_at` | Stable brief ID, positive revision, request lineage, time |
| `goal`, `success_summary` | User outcome and observable success in plain language |
| `delivery` | `answer`, `task`, or `app`; selected by assistant, not mandatory user choice |
| `surfaces` | Subset of `conversation`, `artifact`, `custom_ui`, `background`, `external_update` |
| `inputs` | Selected context/resource references with purpose, source and digest when available |
| `primary_journey` | Ordered user actions and expected observable results |
| `data_needs` | Proposed collections/fields/provenance/retention; may be empty |
| `actions` | Intended behavior with inputs, outputs, external effects and required capabilities |
| `recurrence` | Null or desired trigger/timezone; not an active schedule |
| `constraints` | Supported execution/data location, limits and user preferences |
| `acceptance_examples` | Input/result checks plus essential failure cases |
| `assumptions`, `open_questions`, `unavailable_capabilities` | Explicit uncertainties and boundaries |
| `selected_context_snapshot_id` | Exact bounded context used for planning/building |

The brief is not an authorization grant. Account scope, destinations and effects are resolved separately. A revision records user corrections and supersedes prior assumptions without altering historical runs.

## 3. Source package and action definition

`app.yaml` declares `contract_version`, stable `app_id`, `name`, `description`, `runtime_profile`, `sdk_version`, optional `modules`, `config_schema`, `collections`, `actions`, `capabilities`, optional `ui` and optional `trigger_templates`. It cannot assign grant IDs, secret values, connection credentials, resolved runtime paths or an active release. Trigger templates describe options; only platform activation creates triggers.

The runtime_profile selects an immutable qualified Python dependency profile ID, not a local path or sandbox permission. sdk_version and optional modules (package-name → exact version) must match that profile. An optional UI declaration selects a qualified ui_build_profile and exact kit/bridge versions. Version ranges, floating tags, ambient installs and source-authored grants are forbidden. Core resolves the full dependency closure; section 11 defines the resolved manifest.

Each action includes:

| Field | Meaning |
|---|---|
| `id`, `title`, `description` | Stable machine ID and useful display/assistant descriptions |
| `handler` | `module:function` inside the validated package |
| `input_schema`, `output_schema` | Typed JSON Schema with explicit required fields |
| `capability_requirements` | Versioned operation families and resource/destination needs |
| `effect_class` | Declared `none`, `local_write`, `external_read`, or `external_write`; providers may classify more strictly |
| `invocable_from` | Subset of assistant, UI, manual, trigger; no authority by itself |
| `timeout_seconds` | Requested deadline within the approved runtime profile |
| `retry_class` | `pure`, `idempotent`, or `requires_reconciliation`; platform verifies applicability |

Action inputs and results are schema-validated at invocation/completion. Resolve the actual callable and signature in a disposable validation worker, then execute it. Importing candidate modules in trusted Core is prohibited. No action-ID fallback may conceal a missing handler. CPU-only transformations may be pure; external actions do not become safe merely because the manifest says so.

Collection definitions contain name, field schemas, ownership/provenance conventions, indexes and uniqueness rules. Use logical references. Custom UI declares its entry asset and action/read-view needs, not native privileges. Config fields explicitly identify which changes are settings-only versus rebuild-required.

## 4. BuildRequest and BuildResult

BuildRequest: `build_id`, `attempt_id`, `brief_ref`, optional `base_release_ref`, `context_snapshot_ref`, `template_profile`, `sdk_profile`, `ui_kit_profile`, `dependency_profile`, `validation_plan_ref`, `model_route_ref`, `budget`, `workspace_lease_ref`, `deadline`.

BuildResult: matching identities, `status` (`candidate`, `failed`, `cancelled`), optional `source_package_ref` and digest, normalized events, diagnostics, usage, timestamps and failure category. A candidate is not a ready release. Build states are `queued → building → validating → ready` with optional bounded `repairing → building` cycles and terminal `failed`/`cancelled`. Only Core changes authoritative state. Any unsuccessful required stage prevents `ready`.

VerificationReport records package digest, check IDs, independent behavior evidence, UI evidence if applicable, environment/toolchain, pass/fail/skipped status, unresolved limits and attempt lineage. Required skipped checks block readiness. One aggregate boolean cannot override contradictory stage results. Developer-written tests must not read expected results from candidate implementation.

## 5. Version, Release and activation

Version: `version_id`, `app_id`, `source_digest`, `asset_digest`, resolved action/catalog digest, `dependency_manifest` (section 11), collection schema versions, verification report reference and creation time. It is immutable and contains no mutable user data or secrets.

Release: `release_id`, `app_id`, `version_id`, resolved config snapshot/digest, resource binding references, connection/grant references, model route/budget profile, data schema compatibility, verification reference and creation time. The App stores an active release pointer plus operational state (`active`, `paused`, `quarantined`, `retired`). Current revocation always narrows a Release's effective authority.

Activation requires expected current release, passing checks for the same package bytes, supported runtime, bound required resources, current permissions and compatible data schema. Perform compare-and-swap on the active pointer. A permission expansion or destructive migration must have the appropriate current review. A normal reversible activation within the user's creation request need not add a redundant confirmation step.

## 6. Invocation and execution envelope

Invocation contains `request_id`, an authenticated caller, discriminated owner, `action_id`, `input`, `idempotency_key` where applicable and optional causal run/occurrence reference. Core derives effective authority; caller-supplied owner fields cannot create it.

Owner variants:

- App: `{kind: app, app_id, release_id, action_id}`.
- Task: `{kind: task, task_id, task_revision_id, attempt_id, plan_ref}`.

ExecutionEnvelope contains `run_id`, workspace/principal identity, owner, origin (`user`, `assistant`, `ui`, `trigger`, `repair_test`), exact input/context digests, capabilities/resource bindings, current grant references, provider route, limits/deadline, output scope, immutable snapshot digest and worker lease. Any generated App or Task computation also pins its exact runtime profile ID and dependency-manifest digest; a direct broker-only Task needs no generated-code profile. Dependencies are never re-resolved at invocation. Task capabilities may include qualified browser/HTTP/file actions; no text/files-only restriction remains.

Run states: `queued`, `running`, `waiting_input`, `waiting_approval`, `waiting_connection`, `needs_reconciliation`, `succeeded`, `failed`, `cancelled`, `interrupted`. A wait returns to queued/running only after a verified resolution under current policy. `succeeded` requires declared outputs and evidence of required effects. Worker death produces interrupted or needs_reconciliation depending on dispatch evidence. Terminal failed/cancelled runs are not mutated into a later success; explicit retry creates a new Run linked by `retry_of`.

Each event has `event_id`, `run_id`, monotonically increasing `sequence`, `kind`, `occurred_at`, schema-versioned `payload` and optional operation/step reference. Append state transition plus associated event atomically in the control store. Consumers resume by cursor and tolerate duplicate delivery; sequence is per run, not a global ordering promise.

## 7. Capability operation and effect ledger

CapabilityRequest: `request_id`, `run_id`, authenticated workload token, `operation_id`, capability/operation version, schema-validated input, resource/connection references, optional durable `step_key`, optional idempotency key and deadline. Core supplies the acting principal/owner and derives the effective effect policy. Do not trust worker-supplied credentials or an asserted “read-only” flag.

The authorization intersection is current user authority ∩ execution snapshot ∩ capability profile ∩ connection/resource/destination scope ∩ current grant ∩ budget ∩ approval if required. Validate again at dispatch and after a long wait. Redirects, uploads, downloads and account changes trigger their own scope checks.

Effect states: `prepared`, `awaiting_approval`, `dispatching`, `confirmed`, `failed_before_effect`, `outcome_unknown`, `cancelled_before_dispatch`. Persist intent before dispatch. Approval binds exact run/release or bounded authorized family, account, destination, operation, payload digest and expiry. Changing material fields invalidates the approval. A receipt contains evidence source, provider reference/time and observed outcome, not merely “HTTP 200.”

Timeout/worker death after dispatch means outcome_unknown unless a provider guarantee establishes otherwise. Do not retry blindly. Reconcile via provider idempotency key/status lookup, observed external record or explicit user resolution. Store the evidence and any limits. Cancellation after dispatch cannot claim the external effect was reversed. Every provider maps its outcomes into these semantics.

Capability responses use `completed`, `waiting`, `failed`, or `outcome_unknown`, with operation ID, result/receipt or reason/recovery metadata. Pending human input is not a success result. Provider failures distinguish invalid input, access revoked/expired, unavailable/unsupported, rate limited, timed out, budget exhausted, conflict and internal error.

## 8. Records and artifacts

Record reads use collection ID, typed filter/sort, page cursor and projection. Initial defaults: 100 records per page, maximum 1,000; return a continuation cursor and reject unbounded queries. Aggregation supports count/sum/group on declared fields, with output limits. These defaults are configurable platform policy, not generated code choices.

Create includes validated values and optional unique/idempotency key. Update includes record ID, expected revision and patch; the SQL mutation compares revision atomically. Delete also checks revision. Return the committed revision or a typed conflict. User overrides and source projection updates are separate operations. A batch transaction is limited to one App store; cross-store actions expose partial outcomes.

Artifact metadata: ID, owner, media type, display name, size, digest, provenance, creation time, retention and storage reference. Actual filesystem paths remain internal. Stage bytes with limits, seal/validate, then register. An export resolves a selected destination through the trusted host. Artifact content is not automatically shared across Apps or sent to models.

## 9. Scheduling

Trigger fields: ID, App/action, config/input binding, schedule revision, enabled flag, type (`interval`, `daily`, `weekly`), interval or local wall time/days, IANA timezone, effective start and overlap policy. An occurrence records trigger/revision, intended due time, resolved UTC instant, state and optional Run.

First policy: run once at the first occurrence of an ambiguous repeated local time; skip and record `missed_dst_gap` for a nonexistent local time. Interval triggers use UTC elapsed intervals. Use unique schedule-revision/due keys. One active run per trigger; overlapping occurrences are recorded as skipped, not silently coalesced. Trigger edits invalidate undispatched occurrences of the old revision.

On restart/wake, occurrences whose dispatch time was missed are visible and do not automatically execute. Manual retrigger creates a new Run linked to the missed occurrence and rechecks current authority. Closing a window does not disable triggers; explicitly quitting the runtime stops local execution.

## 10. Compatibility and unsupported behavior

R2 does not require cloud deployment, public webhooks, arbitrary native shell capabilities, a marketplace, broad ambient memory or a second code-generation stack. HTTP action providers and local schedules are alpha requirements; public inbound webhook service is a future extension. Unknown capabilities fail with actionable limits, not generated fake implementations.

All state/authority/storage rules require integration evidence before external use. Required tests are mapped to F-tickets and A-scenarios in the implementation plan. Contracts are deliberately detailed enough to start coding, while exact generated schemas, binary pins and native conformance evidence are implementation outputs rather than invented completed artifacts.

## 11. Dependency profiles and resolved dependency manifest

These are serialized compatibility records, not a custom dependency resolver. uv/pnpm produce locks; Core records and validates their identities. Implementation Blueprint section 10 owns preparation, reuse, upgrade and retention mechanics.

DependencyProfile has required `profile_id` (opaque immutable ID), `kind` (`python_runtime` or `ui_build`), `role` (App/Task compute or the separately qualified trusted tool role), `target` (OS/architecture and exact Python ABI or UI toolchain versions), `locks` (relative lockfile path and SHA-256 pairs), `packages` (exact name/version/artifact SHA-256 entries), `compatibility` (contract/SDK/bridge versions as applicable), and `manifest_sha256`. Derive the manifest digest from UTF-8 compact JSON with recursively sorted object keys, no NaN and sorted locks/packages, omitting manifest_sha256 itself; byte-bearing lock/artifact digests remain hashes of their actual bytes. The ID maps immutably to this digest; any changed lock, target or artifact creates a new identity. Package inventories cover the resolved closure, not only direct imports.

The platform-produced per-Version `dependency_manifest` contains required `runtime_profile_id`, `runtime_profile_manifest_sha256`, `sdk` (exact name/version/artifact SHA-256), `modules` (possibly empty exact package list), and nullable `ui_build` (profile ID/manifest SHA-256, exact kit and bridge package identities). Both profile and per-Version manifest bytes are sealed and hashed in package.index.json. No local installation paths, grants or secret values appear in either portable record. A UI-less App has ui_build=null. Profiles are compatible only when target, package pins and interface requirements pass the qualified compatibility checks; a version range cannot silently select a replacement.

Host-local installation rows hold profile_id, local location reference, state (`preparing`, `ready`, `quarantined`, `deleting`, `failed`), artifact integrity/evidence and creation/update times. Only ready, verified, supported profiles can acquire new execution leases. Current runs and retained Versions hold references preventing deletion. Source/code/profile manifests remain immutable; local availability/support state can change. Suspected compromise quarantines the profile and pauses affected execution visibly, with explicit handling of active runs and any unknown external effects.

Candidate validation, activation and invocation must agree on the same dependency manifest/profile identities. A shared package change creates a new profile and new App Version candidate, including when its App source text is unchanged. Different Apps activate independently. A settings-only Release may reuse the same Version and dependency manifest. Rollback requires the exact retained profile plus compatibility with current data and permissions. UI build profiles are needed to rebuild; runtime display consumes already sealed static assets. Do not require Node in a running App worker.
