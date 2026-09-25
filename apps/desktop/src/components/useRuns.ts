import { useCallback, useEffect, useRef, useState } from "react";
import type { Run, RunEvent } from "@alpha/contracts";
import type { CoreClient, SyntheticRunRequest } from "../core/client";

export interface RunView {
  run: Run;
  events: RunEvent[];
}

/** Keeps a durable-cursor view of runs: initial list, then live SSE updates with reconnect. */
export function useRuns(client: CoreClient) {
  const [runs, setRuns] = useState<Map<string, RunView>>(new Map());
  const [error, setError] = useState<string | null>(null);
  const cursor = useRef(0);

  useEffect(() => {
    let disposed = false;
    const controller = new AbortController();
    (async () => {
      try {
        const initial = await client.listRuns();
        if (disposed) return;
        setRuns(new Map(initial.map((run) => [run.run_id, { run, events: [] }])));
      } catch (e) {
        if (!disposed) setError(`Could not load runs: ${String(e)}`);
      }
      while (!disposed) {
        try {
          await client.stream(
            cursor.current,
            (item) => {
              cursor.current = Math.max(cursor.current, item.cursor);
              setRuns((previous) => {
                const next = new Map(previous);
                const existing = next.get(item.run.run_id);
                const events = existing ? existing.events : [];
                const known = events.some((e) => e.event_id === item.event.event_id);
                next.set(item.run.run_id, {
                  run: item.run,
                  events: known ? events : [...events, item.event],
                });
                return next;
              });
            },
            controller.signal,
          );
        } catch (e) {
          if (disposed || controller.signal.aborted) return;
          setError(`Live updates interrupted, reconnecting: ${String(e)}`);
          await new Promise((resolve) => setTimeout(resolve, 1000));
        }
      }
    })();
    return () => {
      disposed = true;
      controller.abort();
    };
  }, [client]);

  const submit = useCallback(
    async (request: SyntheticRunRequest) => {
      setError(null);
      try {
        const run = await client.createRun(request);
        setRuns((previous) => {
          const next = new Map(previous);
          if (!next.has(run.run_id)) next.set(run.run_id, { run, events: [] });
          return next;
        });
      } catch (e) {
        setError(`Could not start: ${String(e)}`);
      }
    },
    [client],
  );

  const cancel = useCallback(
    async (runId: string) => {
      setError(null);
      try {
        const run = await client.cancelRun(runId);
        setRuns((previous) => {
          const next = new Map(previous);
          const existing = next.get(runId);
          next.set(runId, { run, events: existing ? existing.events : [] });
          return next;
        });
      } catch (e) {
        setError(`Could not cancel: ${String(e)}`);
      }
    },
    [client],
  );

  const ordered = [...runs.values()].sort((a, b) => (a.run.created_at < b.run.created_at ? 1 : -1));
  return { runs: ordered, error, submit, cancel };
}
