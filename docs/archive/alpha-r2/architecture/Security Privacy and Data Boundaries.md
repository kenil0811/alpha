# Security, privacy and data boundaries

Baseline R2 · 24 September 2026. Owns trust/authority and information handling. Execution and effect states are defined in Current Release Specification. Qualification work is F03/F15/F20/F21, not assumed completed by this design.

## 1. Trust roles

The user grants bounded authority through trusted shell/native flows. Core owns policy, records and lifecycle. Models propose decisions. Builder and generated code are untrusted execution. Generated UI is unprivileged presentation. Website/file content is untrusted evidence. External providers return observations whose meaning must be checked.

No role automatically inherits another's authority. Building an App does not authorize using all accounts. A selected file does not grant its parent directory. Login does not authorize every site action. A release snapshot cannot revive a revoked grant. Reading instructions in a webpage cannot authorize following them. A generated success message cannot prove an external effect.

## 2. Enforcement and minimal authority

Every request is bound to authenticated workspace/principal, Task/App owner, Run, operation and current resource/connection grant. Workers use short-lived scoped tokens; Core derives identity from them, not from asserted App IDs. Recheck at dispatch and after waits. Bind consequential approval to account, destination, payload and expiry; ordinary clarification is not approval.

Re-use existing applicable user authorization. Ask only when required scope expands or an action needs an unresolved decision. The goal is useful bounded operation, not repetitive permission prompts. UI explanations must make the actual consequence clear.

Platform enforcement covers budgets, destinations, file handles, data owners, action receipts and revocation. Prompt instructions and harness permission settings are supplementary. Unrestricted shell/socket/filesystem access in a generated process would bypass the design, so the private-use profile must prevent it in the actual OS.

## 3. Local execution qualification

F03 tests sandbox-runtime feasibility and the real Tauri generated-UI boundary. F20 qualifies restricted builder/App/parser profiles with actual adversarial probes. Explicit read denials/allowed runtime paths, filesystem writes, outbound sockets, loopback, inherited descriptors, subprocesses, symlinks, archives, resource limits and cancellation are tested. The chosen tool's defaults are not accepted as the product's security policy.

Initial synthetic internal work may run under a disclosed same-user development profile using nonsensitive fixtures. No real personal/account data or external-user distribution under that profile. If restrictions cannot be enforced, select a qualified local replacement or reduce capabilities explicitly. Never silently relax isolation or send data to a remote sandbox. A local VM is a possible fallback decision, not a prerequisite users must install without evidence.

The host launches only registered profiles with typed arguments and an allowlisted environment. No arbitrary JavaScript/native command bridge. Generated UI cannot obtain shell/session secrets or native access and cannot submit a trusted approval. Maintain recognizable trusted chrome outside generated surfaces; visual similarity alone must never create authority.

## 4. Secrets and sessions

Store durable API tokens and connection secrets through Keychain. Generated packages receive opaque connection handles, not secret bytes. The trusted model gateway injects provider credentials; build/run-scoped gateway tokens have route and budget limits. Disable ambient harness configuration/plugins/sharing. Logs, prompts, exports and source cannot include provider keys.

Browser profiles are separate provider-owned protected stores. Do not copy the user's ordinary browser profile or disclose cookie/storage files to the builder. Dedicated sessions and visible login/takeover avoid credential collection in chat. Account switching, expiry and revocation are explicit. Retained screenshots/downloads may contain sensitive data; scope and redact them before repair context.

## 5. Network, files and effects

Use logical selected-file/folder handles, resolve them at operation time and validate traversal/symlinks against the current grant. Complex parsers run in bounded no-network helpers. File export is a separate selected-destination operation. Generated packages cannot infer access from an absolute path supplied in a prompt.

HTTP/browser providers enforce qualified destinations and operation semantics. Check redirects/resolved addresses, private networks, upload/download scope, methods and accounts. Generic browser clicks and form fills may cause autosave or submission; treat unknown effects conservatively and use a supported review/handoff path. Prevent direct generated network calls from bypassing the broker.

Persist external intent before dispatch; record receipts and uncertainty. Do not automatically retry a potentially completed write. Cancellation prevents further work but cannot undo a completed remote action. Uncertain outcomes remain visible until reconciled. Approval must not authorize a changed payload accidentally.

## 6. Storage and disclosures

Default durable state remains on the Mac. Remote models/services may process explicitly selected information; disclose destination/data category. “Local” does not mean offline inference. No cloud synchronization or remote build persistence is silently enabled.

The initial private-alpha at-rest profile requires OS-backed encrypted storage, such as FileVault or a qualified encrypted volume, plus a private application directory and Keychain. Verify setup and explain limits: disk encryption does not isolate an unlocked user's processes or encrypt exported copies automatically. R2 does not claim an independently password-locked encrypted database vault. If a future audience needs that, qualify a dedicated encrypted-store design before promising it.

Exports/backups make data movement explicit. Default secrets are excluded; require secure reattachment on restore. Keep ordinary diagnostic events sanitized and bounded, with more detailed capture opt-in when useful. Initial evidence retention defaults and unresolved-effect exceptions are owned by Domain and Persistence Model.

## 7. Verification matrix

| Threat/failure | Required evidence |
|---|---|
| Cross-App data or credential reads | Worker/UI probes denied by actual enforcement |
| Localhost/network bypass | Direct sockets and alternate routes denied; only authorized broker operations succeed |
| Prompt injection in page/file | Retrieved instructions cannot expand grants or authorize effects |
| Approval replay/stale payload | Wrong run/account/digest/expiry rejected |
| Retry after timeout | Unknown effect goes to reconciliation, without duplicate dispatch |
| Revocation during wait | Resume fails current authorization check |
| Candidate/path escape | Traversal/symlink/archive probes fail; live data unchanged |
| Builder/candidate failure | Current release/data preserved, no false success |
| Crash or update failure | Restore/reconciliation recovers known state and visible uncertainty |

These requirements are necessary because Alpha executes generated work on a personal machine. They do not imply enterprise certification or perfect security, and they do not replace usefulness/UX gates.

## Shared dependency protection

Trusted install/profile management is the only writer of common runtimes, package artifacts and caches. Generated builders/App workers cannot overwrite, rename, poison or gain authority through those shared paths, including hardlink/symlink targets, bytecode and library caches. Writable scratch is lease-local. Exact profile pins govern both validation and invocation; missing/corrupt/unsupported profiles fail visibly rather than falling back to ambient or newer packages. F20 must qualify the actual OS boundary. Cache reuse and read-only flags alone are insufficient evidence. Shared code does not imply common record, credential or browser-session access.
