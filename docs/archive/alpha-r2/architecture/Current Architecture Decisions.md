# Current architecture decisions

Baseline R2 · 24 September 2026. Replaces the earlier decision set for clean-start implementation. Historical versions retain previous rationales. “Selected” means a design choice; native/runtime qualification remains pending.

| ID | Decision | Tradeoff / consequence |
|---|---|---|
| D01 | General end-user creation platform; examples are evaluations | Prevents domain-specific demos from substituting for the product |
| D02 | Task for one-off, App for reusable, common Run/broker | More than app generation without separate lifecycle engines |
| D03 | Generated Python plus optional React on supported SDK/kit | Broad customization with a manageable runtime, not arbitrary stacks |
| D04 | Shared action definitions for UI/assistant/triggers | Consistent behavior and policy; real symbol/schema validation is required |
| D05 | Tauri/React + modular Python Core | Adds packaging/language boundaries; qualifies them before broad implementation |
| D06 | OpenCode first builder candidate behind thin adapter | Provider flexibility; process/config/credential lifecycle must be qualified |
| D07 | Claude Agent SDK fallback, no mandatory dual-harness race | Less early integration work; switch based on evidence rather than sunk effort |
| D08 | Pydantic AI for typed model/tool plumbing | Platform owns durable state, limits and authority |
| D09 | Code versions separate from records/artifacts | Safe repair/rollback requires schema compatibility and migration gates |
| D10 | SQLite and supervised workers, no distributed engine initially | Simple local operations; cross-store/effect recovery must be explicit |
| D11 | Browser is a governed provider usable by Task and App | More flexible than text/files-only Tasks; account/effect boundaries are essential |
| D12 | Local scheduling, visible missed work, manual retrigger | No unexpected catch-up after quit/sleep; cloud needed for eventual availability |
| D13 | Sandbox provider qualifies early; private release blocks on enforcement | Internal fixtures can progress without pretending folder isolation is security |
| D14 | Local at-rest profile uses OS-backed encrypted storage and Keychain | No application-vault claim; exports/backups require separate treatment |
| D15 | Real generation and UX evaluated before broad capability expansion | Initial engagement stops at M1 for product review |
| D16 | Shared services and exact SDK/UI/module packages; immutable managed profiles | Reuse dependencies without sharing writable environments or app authority |
| D17 | uv and pnpm workspaces; existing SQLite inventory | Reuse mature installation/cache tools without a registry service or custom resolver |
| D18 | Candidate-based dependency upgrades with per-App evidence | Fix common source once; preserve working releases and data when a consumer fails |

## Alternatives considered

An all-TypeScript Core would reduce language boundaries and suit the builder ecosystem. Python remains the initial choice for generated file/data processing and typed model workflows, with packaging explicitly tested in F01. If packaging evidence defeats that choice, decide early; do not keep two Cores. Electron could simplify Node lifecycle but changes native footprint/security integration; no evidence yet justifies replacing Tauri. A workflow graph engine could add explicit execution topology, but durable step/effect boundaries meet the initial needs without requiring nontechnical users to design graphs.

Agent-native frameworks can inform shared action/data interfaces, but adopting a full web/auth/database platform would not by itself solve end-user generation, local execution, verification or repair. We adopt the useful principle, not an unrelated product stack.

## Verified upstream facts and source basis

Research checked 24 September 2026. These facts support candidate choices; they are not measurements of Alpha compatibility. Verify exact versions during qualification.

- OpenCode documents a headless HTTP server, OpenAPI surface, sessions/events/abort and configurable loopback binding/password. That supports a thin external adapter. Its permissions start permissively, so Alpha must supply an explicit profile rather than inherit defaults. [Server documentation](https://opencode.ai/docs/server/), [permissions documentation](https://opencode.ai/docs/permissions/).
- OpenCode lists configurable model providers/base URLs. Gateway and BYOK compatibility still need an actual run with the pinned provider/harness combination. [Provider documentation](https://opencode.ai/docs/providers/).
- Claude Agent SDK offers Python/TypeScript access to an agent with file, command and tool capabilities. Its authentication terms distinguish API access from consumer login; no consumer subscription is assumed to be an embeddable product entitlement. [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview).
- Pydantic AI supplies typed tool/output and model-provider abstractions. Our choice to keep run state and policy in Core is an Alpha design decision. [Pydantic AI overview](https://pydantic.dev/docs/ai/overview/).
- Tauri documents sidecars and web/native capability controls. Those controls do not establish isolation of arbitrary Python worker code; that is a separate qualification requirement. [Sidecars](https://v2.tauri.app/develop/sidecar/), [capabilities](https://v2.tauri.app/security/capabilities/).
- sandbox-runtime provides OS-level filesystem/network restrictions and describes limitations. Its documented default allows unrestricted reads; Alpha needs a restrictive profile and adversarial tests. Broad allowed destinations can still carry unwanted traffic. [Repository and limitations](https://github.com/anthropics/sandbox-runtime).
- Browser authentication state can carry cookies/headers usable to impersonate an account. Alpha therefore retains it with the trusted browser provider. [Playwright authentication](https://playwright.dev/python/docs/auth).
- SQLite provides transactional behavior, but correct revision checks remain our responsibility. [SQLite transactions](https://www.sqlite.org/transactional.html).
- Builder.io's agent-native project illustrates shared capability/data interfaces. It is a reference for a design principle, not proof of Alpha's creation lifecycle. [Official repository](https://github.com/BuilderIO/agent-native).

Dependency-management source check, 25 September 2026: [uv cache](https://docs.astral.sh/uv/concepts/cache/), [uv project synchronization](https://docs.astral.sh/uv/concepts/projects/sync/), and [pnpm dependency layout](https://pnpm.io/symlinked-node-modules-structure). These support using existing cache/install tooling. Alpha's immutable-profile, direct-interpreter startup and isolated-writable-state requirements are design decisions, not security guarantees supplied by those caches. Qualify exact tool versions in F01/F05/F07.

## Bounded unresolved choices

F01 records supported OS/toolchain and bundled-runtime feasibility. F02 selects the qualified exact builder/model/gateway route. F03 tests the generated-UI mechanism and sandbox candidate; F20 completes the private-use profile. F14 records supported browser/source profiles. F22 qualifies redistributable dependencies and signed delivery. Each has a deadline, evidence and failure path in the plan. None is an open-ended research prerequisite to every other task.
