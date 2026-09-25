# Code ownership and interfaces

Baseline R2 · 24 September 2026. Implementation Blueprint owns the directory map. This file owns the minimum interface responsibilities; it is not a request to scaffold all classes immediately.

| Interface/service | Minimum behavior | Owner |
|---|---|---|
| AssistantService | Clarify, route, revise brief, request build/Task/action | assistant |
| BuildService / BuilderHarness | Prepare workspace, start/events/cancel/result, normalize outcome | builds / builder worker |
| CandidateVerifier | Check paths/schema/bindings, run independent behavior/UI checks | builds / validator worker |
| ReleaseService | Seal, resolve, activate with expected pointer, compatible rollback | solutions |
| RunCoordinator | Create envelope, dispatch worker, persist steps/events, wait/reconcile/cancel | execution |
| CapabilityBroker | Authenticate workload, intersect grants, validate policy/budget and dispatch | capabilities |
| ModelGateway | Route, validate/bound calls, inject credentials, record usage | models |
| RecordService | Validate/query/write with revisions, transactions and idempotency | data |
| ArtifactService | Stage/seal/read/export through scoped handles | artifacts |
| EffectService | Intent/approval/dispatch/receipt/unknown-outcome reconciliation | capabilities |
| BrowserProvider | Dedicated session, inspect/read/fill/action/takeover and receipts | browser worker |
| WorkerSupervisor / SandboxProvider | Registered profiles, launch/lease/cancel/cleanup and enforced boundary | native host/adapters |
| ScheduleService / Clock | Due occurrence creation, pause/missed/manual retrigger | schedules |
| SecretStore / FileGrantResolver | Native secret references and selected paths/handles | native adapters |

Use concrete small implementations first. Introduce abstraction at an actual replaceable/provider/process boundary, not every internal helper. Functions and typed records are preferable to speculative inheritance. Unit-of-work boundaries must match real databases; do not invent a transaction spanning files, providers and multiple SQLite stores.
