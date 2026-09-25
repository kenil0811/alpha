import type { RunView } from "./useRuns";

const ACTIVE = new Set(["queued", "running"]);

const STATE_LABEL: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
  interrupted: "Interrupted",
  waiting_input: "Needs your input",
  waiting_approval: "Needs approval",
  waiting_connection: "Needs a connection",
  needs_reconciliation: "Outcome unknown",
};

export function RunList({ runs, onCancel }: { runs: RunView[]; onCancel: (runId: string) => Promise<void> }) {
  if (runs.length === 0) {
    return <p className="empty">Nothing has run yet. Send some text to see the worker path in action.</p>;
  }
  return (
    <ul className="runs" aria-label="Runs">
      {runs.map(({ run, events }) => {
        const output = run.output as Record<string, unknown> | null;
        const progress = events.filter((e) => e.kind === "worker.progress").length;
        return (
          <li className="run" key={run.run_id} data-state={run.state}>
            <div className="run__head">
              <span className={`badge badge--${run.state}`}>{STATE_LABEL[run.state] ?? run.state}</span>
              <span className="run__id">{run.run_id}</span>
              {ACTIVE.has(run.state) ? (
                <button type="button" className="button" onClick={() => onCancel(run.run_id)}>
                  Cancel
                </button>
              ) : null}
            </div>
            {output ? (
              <pre className="run__output">{`${String(output.upper ?? "")}\n${String(output.words ?? 0)} words · ${String(output.characters ?? 0)} characters`}</pre>
            ) : null}
            {run.terminal_reason && run.state !== "succeeded" ? (
              <div className="notice">Reason: {describeReason(run.terminal_reason)}</div>
            ) : null}
            <details className="run__events">
              <summary>
                {events.length} events · {progress} progress updates
              </summary>
              <ol>
                {events.map((e) => (
                  <li key={e.event_id}>
                    <code>{e.sequence}</code> {e.kind} <span>{e.occurred_at}</span>
                  </li>
                ))}
              </ol>
            </details>
          </li>
        );
      })}
    </ul>
  );
}

function describeReason(reason: string): string {
  switch (reason) {
    case "worker_error":
      return "the worker reported an error";
    case "worker_exit_nonzero":
      return "the worker stopped unexpectedly";
    case "worker_exit_without_result":
      return "the worker finished without producing a result";
    case "timeout_exceeded":
      return "the worker was stopped after exceeding its time limit";
    case "worker_killed":
      return "the worker was stopped by a signal";
    case "cancelled_by_user":
      return "you cancelled it";
    case "runtime_quit":
      return "Alpha was quit while it was running; it did not resume automatically";
    case "core_restarted_worker_orphaned":
    case "core_restarted_worker_lost":
    case "core_restarted_no_lease":
      return "the runtime restarted while it was running; it did not resume automatically";
    default:
      return reason;
  }
}
