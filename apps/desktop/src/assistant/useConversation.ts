import { useCallback, useEffect, useRef, useState } from "react";
import type { Conversation, ConversationReply, CoreClient } from "../core/client";

/** One conversation at a time in the shell; polls while the assistant is thinking. */
export function useConversation(client: CoreClient) {
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const active = useRef<string | null>(null);

  useEffect(() => {
    if (!conversation || conversation.state !== "thinking") return;
    const id = conversation.conversation_id;
    active.current = id;
    let cancelled = false;
    const tick = async () => {
      try {
        const next = await client.conversation(id);
        if (!cancelled && active.current === id) setConversation(next);
      } catch (e) {
        if (!cancelled) setError(`Lost track of the conversation: ${String(e)}`);
      }
    };
    const timer = setInterval(tick, 1000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [client, conversation]);

  const start = useCallback(
    async (text: string) => {
      setError(null);
      setBusy(true);
      try {
        const created = await client.startConversation(text);
        setConversation(created);
      } catch (e) {
        setError(`Could not start: ${String(e)}`);
      } finally {
        setBusy(false);
      }
    },
    [client],
  );

  const reply = useCallback(
    async (body: ConversationReply) => {
      if (!conversation) return;
      setError(null);
      setBusy(true);
      try {
        const next = await client.replyConversation(conversation.conversation_id, body);
        setConversation(next);
      } catch (e) {
        setError(`Could not send: ${String(e)}`);
      } finally {
        setBusy(false);
      }
    },
    [client, conversation],
  );

  const reset = useCallback(() => {
    active.current = null;
    setConversation(null);
    setError(null);
  }, []);

  return { conversation, error, busy, start, reply, reset };
}
