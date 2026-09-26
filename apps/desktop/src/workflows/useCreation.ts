import { useCallback, useEffect, useState } from "react";
import { CREATION_DONE, type Creation, type WorkflowsClient } from "../core/client";
import { usePoll } from "../core/usePoll";

/** The creation for a conversation's current brief revision, followed until it finishes. Core
 *  owns the creation, so leaving this view and coming back (or restarting Alpha) finds it again. */
export function useCreation(client: WorkflowsClient, conversationId: string, briefRevision: number | null, pollMs = 1000) {
  const [creation, setCreation] = useState<Creation | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setCreation(null);
    setLoaded(false);
    client
      .conversationCreations(conversationId)
      .then((all) => {
        if (cancelled) return;
        const mine = all.filter((c) => c.brief_revision === briefRevision);
        setCreation(mine.length ? mine[mine.length - 1] : null);
        setLoaded(true);
      })
      .catch(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [client, conversationId, briefRevision]);

  const following = creation && !CREATION_DONE.has(creation.state) ? creation.creation_id : null;
  const { reconnecting, refresh } = usePoll(following, () => client.creation(following!), setCreation, pollMs);

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

  return { creation, loaded, error, busy, reconnecting, refresh, start, cancel };
}
