import { useCallback, useEffect, useRef, useState } from "react";
import { CREATION_DONE, type Creation, type WorkflowsClient } from "../core/client";

/** The creation for a conversation's current brief revision, followed until it finishes. */
export function useCreation(client: WorkflowsClient, conversationId: string, briefRevision: number | null, pollMs = 1000) {
  const [creation, setCreation] = useState<Creation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setCreation(null);
    client
      .conversationCreations(conversationId)
      .then((all) => {
        if (cancelled) return;
        const mine = all.filter((c) => c.brief_revision === briefRevision);
        setCreation(mine.length ? mine[mine.length - 1] : null);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [client, conversationId, briefRevision]);

  useEffect(() => {
    if (!creation || CREATION_DONE.has(creation.state)) return;
    timer.current = window.setTimeout(() => {
      client
        .creation(creation.creation_id)
        .then(setCreation)
        .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
    }, pollMs);
    return () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    };
  }, [client, creation, pollMs]);

  const start = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setCreation(await client.startCreation(conversationId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [client, conversationId]);

  const cancel = useCallback(async () => {
    if (!creation) return;
    try {
      setCreation(await client.cancelCreation(creation.creation_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [client, creation]);

  return { creation, error, busy, start, cancel };
}
