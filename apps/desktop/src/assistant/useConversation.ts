import { useCallback, useEffect, useState } from "react";
import type { Conversation, ConversationReply, CoreClient } from "../core/client";
import { usePoll } from "../core/usePoll";

/**
 * The selected conversation, loaded from Core. The selection itself lives outside the panel
 * (`selectedId`/`onSelect`), so leaving the Assistant and coming back, or reopening Alpha, shows
 * the same conversation. Polls while the assistant is thinking and keeps polling through a
 * temporary connection failure.
 */
export function useConversation(client: CoreClient, selectedId: string | null, onSelect: (id: string | null) => void) {
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!selectedId) {
      setConversation(null);
      return;
    }
    if (conversation?.conversation_id === selectedId) return;
    let cancelled = false;
    setLoading(true);
    client
      .conversation(selectedId)
      .then((found) => {
        if (!cancelled) setConversation(found);
      })
      .catch(() => {
        if (!cancelled) onSelect(null); // gone (another data directory, or removed)
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client, selectedId, conversation?.conversation_id, onSelect]);

  const thinking = conversation?.state === "thinking" ? conversation.conversation_id : null;
  const { reconnecting } = usePoll(thinking, () => client.conversation(thinking!), setConversation);

  const act = useCallback(
    async (what: string, call: () => Promise<Conversation>) => {
      setError(null);
      setBusy(true);
      try {
        const next = await call();
        setConversation(next);
        onSelect(next.conversation_id);
      } catch (e) {
        setError(`Could not ${what}: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setBusy(false);
      }
    },
    [onSelect],
  );

  const start = useCallback((text: string) => act("start", () => client.startConversation(text)), [act, client]);
  const reply = useCallback(
    (body: ConversationReply) => (conversation ? act("send", () => client.replyConversation(conversation.conversation_id, body)) : Promise.resolve()),
    [act, client, conversation],
  );
  const retry = useCallback(
    () => (conversation ? act("try again", () => client.retryConversation(conversation.conversation_id)) : Promise.resolve()),
    [act, client, conversation],
  );
  const reset = useCallback(() => {
    setConversation(null);
    setError(null);
    onSelect(null);
  }, [onSelect]);

  return { conversation, loading, error, busy, reconnecting, start, reply, retry, reset };
}
