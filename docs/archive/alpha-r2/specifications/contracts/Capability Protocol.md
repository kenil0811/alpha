# Capability protocol

Baseline R2 · contract 0.2. Current Release Specification sections 6–8 own payloads and effect states.

Task attempts and App runs use the same broker with distinct authenticated owner variants. A capability has versioned operations, input/output schemas, provider-enforced effect classification, resource/destination scope, required connection/grant, limits, receipts and conformance tests. A method name or generated “read-only” assertion is insufficient policy.

The broker authenticates workload → validates input → resolves current ownership/grants → checks destination/account and limits → obtains any necessary bound approval → durably prepares effect → dispatches → stores receipt or uncertainty. Re-evaluate after waits, redirects and changed payloads. Unknown fields/operations cannot grant fallback access.

Model, record, artifact, selected-file, HTTP and browser operations are first profiles. New native/third-party providers require explicit qualification. Generated code can compose existing operations but cannot install a privileged provider or bypass the broker with direct sockets. Waits are durable; no blocked human request must hold an unbounded worker indefinitely.

External write retries require verified provider idempotency or reconciliation. A timeout after dispatch is outcome_unknown. Revocation fences new requests immediately and cancels active work where possible; completed external effects remain real. See the implementation plan's F13–F15/F20 tests.
