# Run state and event kernel

Baseline R2 · contract 0.2. Current Release Specification sections 6–7 own states, owner variants, event fields and effect outcomes.

Use one durable Run model for Task attempts and App actions, with explicit owner identity. Record input/execution snapshots, worker lease, timestamps, outputs and terminal reason. Event sequence is monotonically increasing per Run. Append associated state/event changes atomically. SSE/observers may deliver duplicates; consumers use cursor/event ID to deduplicate.

Persist steps only at real restart/provider/human boundaries. Stable step keys bind input digest, completion status and result/receipt handle. Reusing a completed key with different input fails. Persist nondeterministic decisions before external effects. Arbitrary Python stacks are not automatically resumable.

Unexpected worker loss marks interrupted unless external dispatch is unresolved, in which case it requires reconciliation. Waiting work is durable and rechecks current authority before continuation. Cancellation stops future work and process descendants but does not erase completed effects. A retried terminal run has a new ID and lineage; do not rewrite history into success.
