# Domain and persistence model

Baseline R2 · 24 September 2026. Owns storage relationships and integrity rules. Field-level external contracts and state machines are in Current Release Specification.

## Entities

| Entity | Durable meaning | Relationship |
|---|---|---|
| Workspace | Local user-owned project/account boundary | Owns Apps, Tasks, connections, grants and Activity |
| Conversation | Request/clarification history and selected context references | Can lead to many Tasks or one/more Apps; chat itself is not authority |
| SolutionBrief revision | Immutable understood goal, assumptions and acceptance | Parent of a Build or Task revision |
| App | Stable identity for reusable work | Owns records/config/triggers and references active release |
| Build / attempt | Candidate construction plus all verification/repair evidence | References brief, base release, route and workspace lease |
| DependencyProfile / installation | Immutable lock/artifact/compatibility manifest plus host-local install state | Referenced by Versions, Task plans and active build/run leases; shared read-only |
| Version | Immutable source/build output with content digest | Contains code/schema/UI/dependency compatibility, not credentials/data |
| Release | Immutable resolved version/config/grant snapshot | An App's current pointer selects it; active/paused state is separate |
| Task revision / attempt | One-off plan and execution history | References its Run and results, without a hidden App |
| Run | Durable execution identity and state | Owner is discriminated Task attempt or App release/action |
| Step / Run event | Checkpoint output and append-only progress | Stable step keys and per-run event sequence |
| Effect / approval / receipt | Intent, authorization and observed external outcome | Bound to exact run/operation/account/payload |
| Collection schema / record | User data definition and mutable items | Scoped to App or explicitly scoped Task scratch; never a code directory |
| Artifact | Immutable output/input blob with metadata/digest | Scoped owners and provenance, retention and export |
| Connection | Account/provider metadata plus secret reference | Grants authorize use; no plaintext secret field |
| Grant | Current bounded resource/action authority | Revocable; release snapshots do not override revocation |
| Trigger / occurrence | Recurrence definition and due/missed/run identity | Unique schedule revision plus due time, linked Run if dispatched |

Use opaque IDs, UTC timestamps and explicit schema/contract versions. Store IANA timezone separately where a user's day or schedule requires it. Content hashes identify bytes, not authorization. Record immutable snapshots where behavior must be reconstructable; avoid copying every table into every Run.

## Initial storage layout

One private platform data directory contains control.sqlite, per-App record stores, sealed versions, artifacts and temporary workspaces. Keychain stores durable secrets; browser session storage has a separate protected provider-owned directory. Exact native paths are resolved by the host and never included in portable packages.

The control store holds conversations/brief metadata, lifecycle entities, grants, runs/events/effects, schedule occurrences and manifests. Store dependency profiles, installation status and per-Version resolved package/profile references here as well; no separate dependency database or registry service. Profile preparation/deletion has recoverable staging states and lease/reference checks as defined in Implementation Blueprint section 10. Each App record store holds collection/schema metadata, validated JSON rows, revisions, indexes and local operation-idempotency records. A Task has isolated scratch/output scope, not ambient access to all App stores. Blob contents live outside SQLite with a staged-write/content-hash registration protocol.

## Integrity rules

- Schema validation occurs in trusted data services. Generated code cannot disable it.
- Revision updates check expected revision atomically in SQL and increment on success. Zero affected rows is a conflict/missing-record outcome, never success.
- Uniqueness/idempotency is scoped to owner, collection and operation semantics. A reused key with different payload is rejected.
- Local batches commit in one App store transaction. Multiple stores and external providers do not form an atomic transaction.
- Source-owned fields/provenance are distinct from user-owned decisions and overrides. Ingestion only updates its declared source projection; it cannot reset user state.
- Staged artifacts and sealed versions become visible only after durable registration. Reconciliation removes abandoned temporary files and resolves incomplete promotions.
- Release activation uses expected-current-release comparison and a migration fence. A stale candidate cannot silently replace a newer release.
- In-flight runs pin version/config; current revocation still applies. Do not change code under a running process.

## Schema changes

Additive optional fields/indexes are the first supported migration profile. Required-field additions need defaults/backfill validation. Renames, type changes, deletions and semantic transforms are review-required and may be rejected as unsupported until the migration runner qualifies them. Never run arbitrary generated SQL in Core.

Before mutation: quiesce relevant writes, snapshot/backup, validate on a copy and record the migration operation. Apply with a versioned journal and recover after a crash. Only activate code compatible with the committed schema. A rollback must satisfy the current schema; restoring an older database is a separate explicit operation with newer-data-loss implications.

## Retention and recovery

Keep business data until user deletion/export policy says otherwise. Keep sanitized run evidence for an initial configurable 30-day default; retain unresolved effect receipts until resolution and expose that exception. Screenshots/raw source captures default to shorter 7-day retention where no unresolved issue requires them. Treat these as initial product settings, not legal retention advice. Deleting evidence may reduce future repair fidelity; explain that tradeoff.

Backups include a consistent control snapshot, referenced App stores, version/profile manifests, exact locks and blobs, including redistributable profile artifacts or a verified offline restore source. A restore cannot silently resolve newer packages; an unavailable exact profile blocks affected execution and is reported precisely. Pause writes or use a coordinated snapshot protocol; copying live database files blindly is insufficient. Restore validates hashes/compatibility and leaves schedules paused until inspected. Secrets are reattached through the secure store rather than embedded in a portable unencrypted export.
