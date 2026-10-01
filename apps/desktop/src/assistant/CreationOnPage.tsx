import { useEffect, useState } from "react";
import { isSessionsClient, type CoreClient } from "../core/client";
import { ConversationCard } from "./ConversationCard";

/** The project being made, on the project's own page: the questions, the research and options,
 *  the brief and the build all show here, and the chat only points to it. Follows the newest
 *  creation card in the project's session. */
export function CreationOnPage({ client, sessionId, onOpenApp }: { client: CoreClient; sessionId: string | null | undefined; onOpenApp?: (appId: string) => void }) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  useEffect(() => {
    if (!sessionId || !isSessionsClient(client)) return;
    let live = true;
    const look = () =>
      client
        .getSession(sessionId)
        .then((s) => {
          const turn = [...s.turns].reverse().find((t) => t.kind === "work" && t.conversation_id);
          if (live && turn?.conversation_id) setConversationId(turn.conversation_id);
        })
        .catch(() => undefined);
    void look();
    const timer = window.setInterval(() => void look(), 3000);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [client, sessionId]);
  if (!conversationId) return null;
  return (
    <div className="section creation-on-page" aria-label="Making this project">
      <ConversationCard client={client} conversationId={conversationId} onOpenApp={onOpenApp} />
    </div>
  );
}
