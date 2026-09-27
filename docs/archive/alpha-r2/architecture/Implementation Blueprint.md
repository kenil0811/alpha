# Implementation blueprint

Baseline R2 · 24 September 2026. Owns code organization, dependency direction and implementation mechanisms. Build the tickets in Prototype_Scope_and_Acceptance.md; do not implement this document as a large scaffold before the first user-driven generation loop.

## 1. Selected implementation baseline

| Layer | Initial choice | Reason and qualification |
|---|---|---|
| Desktop host | Tauri 2 / Rust | Small native surface for process/OS lifecycle; qualify packaged Python and unprivileged UI in F01/F03 |
| Shell and generated UI | React / TypeScript / Vite | One reusable kit and familiar generated code; compile to static assets, no per-App web server |
| UI foundations | Radix, Tailwind tokens, selected TanStack Table/Query | Accessible primitives, data interaction and cache consistency without a second UI language |
| Trusted Core | Python 3.13 modular monolith, Pydantic models, FastAPI local transport | Typed contracts and a practical environment for file/data/AI workflows; packaging is an early gate |
| Assistant/runtime model loop | Pydantic AI behind ModelGateway and platform tools | Provider plumbing is replaceable; persistent runs, policy and budgets remain platform-owned |
| Builder | OpenCode headless adapter, qualification candidate | Avoid implementing a coding agent; candidate must pass real generation/cancellation/credential/packaging tests |
| Builder fallback | Claude Agent SDK, only if primary candidate is blocked | Do not build both comprehensively before useful product evidence |
| Generated behavior | Python functions using Alpha SDK | Reusable action interface and brokered access; no arbitrary app stack in alpha |
| Storage | SQLite control store plus per-App record stores; artifact files | Simple local operations; explicit cross-store recovery, no assumed distributed transaction |
| Browser | Managed Playwright provider | Dedicated sessions, inspection and takeover; site qualification remains required |
| Local isolation | Pinned sandbox-runtime candidate behind SandboxProvider | F03 feasibility and F20 adversarial/native qualification; no claim from upstream defaults |
| Secrets | macOS Keychain adapter | Durable credentials stay outside generated code and package exports |
| Dependency tooling | uv + pnpm workspaces, exact versions pinned in F01 | Managed installs and cache reuse; immutable release profiles and no per-App runtime installer |

Pin exact supported versions after qualification; do not choose floating “latest” in the implementation. Python 3.13 is the planned line, not proof every native wheel ships successfully. If qualification requires a version change, record the specific evidence and update the profile before later work depends on it.

The desired private-alpha BYOK routes are OpenAI and Anthropic. F02 qualifies one first; F22 qualifies the other before both appear as supported in onboarding. Record the exact chosen models and prices at qualification rather than freezing a speculative model name here. Local models remain a later route subject to quality and capability tests.

## 2. Repository map

| Path | Responsibility | First ticket |
|---|---|---|
| `apps/desktop/src` | Trusted React shell | F01 |
| `apps/desktop/src-tauri` | Native host and OS adapters | F01 |
| `services/core/alpha/assistant` | Intent, clarification, brief and Task planning | F04 |
| `services/core/alpha/builds` | Build orchestration and validation handoff | F02/F07 |
| `services/core/alpha/solutions` | Apps, versions, releases and configuration | F08/F10 |
| `services/core/alpha/execution` | Runs, durable steps, waits, leases and cancellation | F01/F12 |
| `services/core/alpha/capabilities` | Authorization, grants and provider dispatch | F05/F13 |
| `services/core/alpha/models` | Provider routes, scoped gateway and usage | F02 |
| `services/core/alpha/data` | Schemas, records, revisions, migrations | F05 |
| `services/core/alpha/artifacts` | Artifacts, handles, export and retention | F05/F11 |
| `services/core/alpha/connections` | Metadata and secret references | F13 |
| `services/core/alpha/schedules` | Triggers and occurrences | F17 |
| `packages/contracts` | Python contract definitions, exported JSON Schema and generated TS types | Incremental |
| `packages/app-sdk` | Python SDK and worker-side client | F05 |
| `packages/ui-bridge` | Typed generated-UI protocol | F03 |
| `packages/ui-kit` | Tokens, accessible controls and composition examples | F06 |
| `workers/builder` | Harness adapter process/profile | F02 |
| `workers/app` | Generated action runner | F05/F07 |
| `workers/validator` | Candidate tests/build/render checks | F07 |
| `workers/parser` | Bounded document conversion | F11 |
| `workers/browser` | Trusted browser-provider process/profile | F14 |
| `templates/app` | SDK/kit/test bootstrap, no example-domain behavior | F06/F07 |
| `tests` and `evals` | Deterministic tests, native qualification and scored generation cohorts | Incremental |
| `docs/alpha-r2` | Immutable planning snapshot | F01 |
| `docs/development` | Task/evidence packets and implementation decisions | F01 |

These are ownership paths, not instructions to create empty directories/classes. Prefer small functions/services before generic base classes. No separate server/virtual machine per generated App. Workers start for active jobs; static UI is served by the platform.

## 3. Dependency direction

Contracts have no Core/UI imports. SDK and UI bridge depend on contracts. Domain services depend on small storage/worker/provider ports, not native UI. HTTP handlers translate transport only. Native host implements OS/process ports. Generated packages import the public SDK/kit, never Core internals. Providers may call model or browser libraries but may not bypass the capability broker.

The first exercised ports are WorkerSupervisor, BuilderHarness, ModelGateway, RecordStore and ArtifactStore. Add BrowserProvider, SecretStore, FileGrantResolver and SchedulerClock when used. Do not generate a class hierarchy for every noun in the architecture.

Expose a CapabilityCatalog to the assistant/builder with operation descriptions, schemas, available connection types, required grants, supported profile versions and current unavailable reasons. Discover capabilities before planning; a model's prior knowledge of a service is not evidence that Alpha can access it. The catalog contains shared provider affordances, not complete calorie/job workflows.

## 4. Native and local transport

Host launches a registered Core binary/profile with an allowlisted environment and random session credential. Core binds loopback only. Trusted shell requests require authorization and origin checks; do not rely on loopback location as authentication. Use typed HTTP commands and SSE events initially; reconnect from durable event cursors. Native commands accept narrow typed operations, not a shell command string from JavaScript.

Generated UI runs in a sandboxed separate-origin/opaque-origin frame with no Tauri API, no shell token and no direct Core endpoint. Parent establishes a MessageChannel bound to the exact window/session; never authorize arbitrary `postMessage` by the string `origin` alone, particularly for opaque origins. Validate schemas, request IDs and current session grants. Revoke on navigation, release change or close. Deny direct network, forms, popups, downloads and top navigation unless mediated by an explicit bridge operation. F03 must prove this in Tauri's actual WebView, not only Chromium tests.

## 5. Model and builder integration

Keep durable provider keys in Keychain. A trusted gateway injects keys and enforces approved model routes, payload limits, deadlines and cost/usage accounting. Workers receive a short-lived credential bound to their build/run, permitted route and budget. The harness may use its provider protocol through the gateway after exact compatibility is qualified; it receives no general account-management route.

Use a separate builder configuration/home per attempt; do not repurpose the user's HOME or inherit global plugins. Launch loopback-only, with per-build server authentication, no discovery/sharing and no extra CORS origins. Translate lifecycle events into platform events. On cancellation request graceful abort, then terminate the registered process group after a short configured grace period. Record surviving-process failures.

The builder gets a synthetic/copied context projection, not live production storage. Harness permissions supplement OS and broker controls; they do not create authority. Dependency installation is a build-time capability limited to a vetted profile. First profile prebundles SDK, UI kit and common libraries. Newly requested dependencies enter the managed qualification path in section 10; no arbitrary runtime installation or mutable shared environment.

## 6. Build and activation mechanics

Create a workspace lease → materialize brief/context/template → invoke real builder → validate package and dependencies → resolve actual action symbols in a disposable worker → execute independent acceptance checks → render/interact with UI when present → bounded repair → seal package/hash → prepare candidate → activate atomically if expected release/data schema still match.

Builder writes cannot change the validator's tests or release metadata. Candidate tests are useful but supplementary. Any requested permission expansion is a structured difference. Keep builds, checks and activation separate; a failed builder cannot become successful because a later check happens to pass. Staging-to-final moves and control-store references need an explicit crash-recovery journal; do not assume filesystem and SQLite commits are atomic together.

## 7. Runtime mechanics

An invocation resolves the discriminated Task/App owner, validates action input and current grant, records Run plus execution snapshot, and launches a scoped worker. SDK calls carry an authenticated workload identity; Core derives ownership rather than trusting worker-supplied App IDs. Models, records, artifacts, HTTP, files and browsers use the broker. Pure computation stays in the worker.

Use `ctx.step(key, callable)` around retryable/durable work boundaries and store completed outputs or handles. Keys are stable within the Run, not newly random at each re-entry. Persist model decisions whose repetition would change downstream action identity. Re-execution outside a step must be safe computation. Do not claim exactly-once external effects; maintain the effect ledger and uncertainty states.

Limits: one builder concurrently by default, finite worker CPU/memory/time/disk quotas, bounded response sizes and provider call counts, explicit monetary ceilings. Queue overload instead of launching unbounded workers. Expose budgets to the assistant as constraints, but enforce them in trusted services. Default values and scored evaluation limits live in the implementation plan.

Before a model call, reserve a conservative cost estimate from the selected route's configured pricing and token ceilings; reconcile with returned usage. If pricing/usage is unavailable, expose that limit and require an explicit compatible budget policy, rather than claiming a precise spending guarantee. Provider billing after timeouts can be uncertain. Route changes that send data to a different provider require the applicable existing or newly granted scope. Validate structured model output, bound schema-repair attempts and retain the failure rather than coercing invented fields into success.

## 8. Data/query implementation

Core owns schema validation and parameterized queries. Start with a per-App records table keyed by collection/id, revision, payload JSON, timestamps and provenance, plus schema metadata, operation idempotency and indexes for declared fields. Expose a typed filter AST, never arbitrary SQL. Add indexes from real query needs. Support UTC timestamps with IANA timezone interpretation for user-facing days and schedules. Retain source timestamps separately.

Enforce compare-and-swap in the write statement; a pre-read revision check alone is insufficient. Batch mutations in one App store may be transactional. Cross-App operations are separate authorized operations with explicit partial-failure behavior, not implied atomic transactions. Candidate data copies must exclude unnecessary personal information.

## 9. Verification and development commands

`just check` runs formatting/types/contract generation drift and fast deterministic tests. `just test-integration` exercises actual SQLite, processes and bridge/broker boundaries. `just test-ui` checks component states/primary interactions. Add `just qualify-mac`, `just eval-generation` and `just test-browser` only when implemented. Live generation is a separate opt-in command requiring an approved route, budget and attempt count. Native and user-study gates never silently become CI mocks.

Evidence is tied to exact code, package hashes and environment. Keep reported first-pass and repaired success separate. A passing implementation test suite is necessary but not sufficient for generated UX usefulness.


## 10. Shared code, dependencies and maintenance

### Ownership and first implementation

| Shared layer | Maintained once | Per-solution boundary | First ticket |
|---|---|---|---|
| Trusted platform services | Records, artifacts, model gateway, scheduling, connections and provider behavior | Every request rechecks authenticated owner, current resource grants and limits | Consuming service ticket |
| Public packages | Python SDK, UI kit, bridge, contracts and reusable pure functions | Exact package versions; no Core imports or ambient authority | F05/F06 |
| Installed dependency profiles | Managed Python runtime/SDK/library installation and separate UI build toolchain | Separate workers, no writes to shared installation or cache | F05/F07 |
| Generated solution | App-specific rules, schema, mappings and optional UI composition | Immutable code Version; independent mutable data/config/scratch and permissions | F07/F08 |

Use one monorepo. Select uv for Python and pnpm workspaces for TypeScript dependency management; F01 pins exact compatible tool versions and commits lockfiles. They are implementation choices, not end-user tools. Use one default App/Task runtime profile and one matching UI build profile initially. Trusted Core/builder/browser/parser tools have their own qualified profiles where needed; do not expose their dependency sets or authority to App workers. No additional profile family until a concrete capability requires it. No package registry service, marketplace, custom resolver, module federation or network-loaded UI dependency system in this release.

Source ownership stays in packages/app-sdk, packages/ui-kit, packages/ui-bridge and packages/contracts. Put a reusable pure helper in its nearest existing package first; create an additional packages/<name> only after exercised reuse and an independently testable contract justify it. Connector/account effects belong in brokered providers. A helper cannot acquire more authority than its caller. Generated packages import supported public packages and compose components; they must not vendor their implementations or copy Core code. App-specific glue remains in the App. Templates contain bootstrap/composition examples, not private forks of shared packages.

### Profiles and physical reuse

A dependency profile is an immutable definition plus a platform-managed installation. Its identity covers role/kind, OS/architecture, Python ABI or UI toolchain, exact lockfile digests, package artifact digests and SDK/module/bridge compatibility. The resolved profile manifest and serialized fields are defined by Current Release Specification sections 5 and 11. Compatible Apps reference the same installed Python profile; they do not each own a mutable virtual environment. Different incompatible profiles may coexist and reuse uv/pnpm cached artifacts where those tools support it. Do not promise zero duplicated disk bytes across platforms/filesystems.

The trusted build/install path resolves only approved sources, checks locks/artifact identity and installs in staging. Validate, seal, then publish atomically and register ready status in SQLite. Concurrent requests for the same identity use a lock/lease and converge on one published installation. A crash leaves an incomplete staging entry to reconcile, never a usable half-install. Builders may write only their workspace and request managed dependency changes; they cannot edit the common store. Disable undeclared lifecycle scripts and prevent unreviewed binary/toolchain downloads. Package code/scripts execute only in the qualified build profile, never imported into Core to inspect metadata.

At execution, launch the already-installed interpreter directly with a controlled import path/environment. Do not run an auto-syncing package-manager command, resolve versions or install packages on App startup. Exclude user site-packages, ambient PYTHONPATH, editable platform installs and unexpected working-directory imports from released runs. Disable shared-location bytecode writes or redirect them to private scratch. Source and shared profile are read-only to generated workers under the qualified OS boundary; scratch, temporary files and any writable library cache are private per lease. Python module globals remain separate because Apps run in separate processes; killing one lease must not kill another App's worker. Core downtime is a shared service outage and must be reported honestly.

uv and pnpm caches reduce repeated downloads and files. Cache layouts, hardlinks, symlinks and chmod alone do not enforce app isolation; F20 must test that workers cannot alter or replace shared artifacts through any permitted path. Only trusted installation/cleanup code controls those stores. Use supported package-manager operations; never mutate package-store files by hand. Development workspace links are allowed for platform development, but sealed App profiles contain immutable built package artifacts rather than editable links to the repository.

The UI profile supplies fixed React/toolchain/kit/bridge dependencies to a controlled build. Each App produces static assets and requires no Node server. Bundling may duplicate some library bytes across those assets; central source ownership and traceable versions are required, byte-perfect deduplication is not. A UI-kit source change does not hot-swap an existing App's compiled assets. Rebuild and verify affected candidates. Do not add dynamic remote imports to avoid bundle duplication.

### Dependencies outside the default profile

First try a qualified existing capability or package. If a real request needs another dependency, record the exact package/source/version and reason, qualify behavior/licensing/size/native compatibility and install scripts, and produce a new immutable profile. The builder can propose this; it cannot self-grant network, native access or installation. F07 may report a precise unsupported-dependency reason until a profile is qualified. Pin the full closure and validate imports/actions/UI against that profile before activation. Never modify a shared environment in place to make one App work or silently upgrade other consumers.

### Fix and upgrade flow

1. Fix the shared source once; publish a new exact package/profile revision with compatibility notes and meaningful tests. Existing profiles remain immutable.
2. Query Version dependencies in the control store to list affected active, candidate and retained rollback versions. There is no separate registry service or user-facing dependency administration console.
3. Build each affected App's upgrade candidate against the new profile using synthetic/copied data; run its primary behavior and UI checks plus shared-package compatibility checks. A central fix does not bypass per-App verification.
4. Activate each passing candidate independently under expected-current-release and data-schema checks. A failed candidate leaves that App's release and data intact. Existing runs retain their original exact profile. Reuse existing creation/maintenance authority for compatible fixes; permission expansion or destructive change still requires its applicable review.
5. Retain known compatible rollback Versions and their profiles. Roll back code only if compatible with current data; never restore old data automatically. If an old profile is unsafe to run, explicitly pause affected execution and explain the required repair instead of pretending pinned means permanently supported.

A compatible trusted service patch may fix all consumers centrally after contract/regression qualification because Apps call its interface. SDK/library/UI changes are versioned candidate upgrades because their code runs or is compiled with the App. A breaking service change must retain the old interface while consumers migrate, or identify affected consumers and pause them explicitly; no requirement to build a multi-version service fleet. F10 proves two-consumer upgrade behavior and service compatibility failure handling. The user sees an understandable update or repair, not package-manager choices.

### Inventory, retention and scope

Use the existing SQLite control store for profile manifests, installation status, per-Version resolved dependencies and profile references. Paths remain host-local; portable manifests contain hashes/logical identifiers. Runs and builds hold leases on exact profile identities. Track selected/active releases, staged candidates, running leases and retained rollback Versions as strong references. Start with the current and previous compatible release plus explicit retained versions; unresolved effects and active runs may require more. Reachability and lease checks must be in the same serialized transition as marking a profile for deletion, so a new acquisition cannot race cleanup. Delete only unreferenced installations using a recoverable journal; underlying package caches use supported prune operations separately. F22 proves install/cleanup/restart behavior.

Shared data is a different feature. SDK/component/profile sharing never permits another App's records, files, credentials, model history or browser session. Initial App records remain owner-scoped. If a future workflow needs common contacts or inventory, bind an explicit shared resource through the broker with separate read/write grants and ownership semantics; do not make every App store globally readable to obtain code reuse. Do not add a general shared-data subsystem to M1.
