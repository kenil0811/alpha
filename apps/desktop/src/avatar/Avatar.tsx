/**
 * The assistant's avatar: a small panda in the corner of every surface. It shows what the
 * assistant is doing (see state.ts) and opens the assistant when clicked.
 *
 * The art and rig (zazoo/) are ported from Bridge, Vikas Badami's own product
 * (platform/apps/web/src/app/avatar/zazoo at 816c646f, 27 Aug 2026): the ZazooDirector, the
 * SVG rig, the traced mouth/brow parts and the painted panda layers (assets/panda, ~155 KB).
 * Reduced motion shows the static head and no bubble animation.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import type { Conversation, CoreClient, Creation } from "../core/client";
import { isWorkflowsClient } from "../core/client";
import { CompanionZazooFace } from "./zazoo/CompanionZazooFace";
import { ZazooDirector } from "./zazoo/director";
import { DONE_PERFORMANCE, PERFORMANCE, type AvatarView } from "./state";

const BUSY = new Set(["thinking", "building", "working"]);

export function AssistantAvatar({ view, beside, onClick }: { view: AvatarView; beside: boolean; onClick: () => void }) {
  const director = useMemo(() => new ZazooDirector(), []);
  const previous = useRef(view.state);
  useEffect(() => {
    const was = previous.current;
    previous.current = view.state;
    // Work that lands without a problem gets a brief happy beat, then the state's own pose.
    if (BUSY.has(was) && (view.state === "idle" || view.state === "awaiting")) {
      director.perform(DONE_PERFORMANCE);
      const timer = window.setTimeout(() => director.perform(PERFORMANCE[view.state]), 2600);
      return () => window.clearTimeout(timer);
    }
    director.perform(PERFORMANCE[view.state]);
  }, [director, view.state]);
  return (
    <button
      type="button"
      className={`avatar avatar--${view.state}${beside ? " avatar--beside" : ""}`}
      aria-label="Assistant"
      aria-describedby="avatar-state"
      data-state={view.state}
      onClick={onClick}
    >
      <span className="avatar__face" aria-hidden="true">
        <CompanionZazooFace director={director} size={56} label="" />
      </span>
      <span className="avatar__dot" aria-hidden="true" />
      <span id="avatar-state" className="avatar__bubble">
        {view.text}
      </span>
    </button>
  );
}

/** The conversation in front of the person and Core's recent creations, asked every few
 *  seconds so the avatar follows work even while the assistant panel is closed. */
export function useAvatarSignals(client: CoreClient | null, conversationId: string | null, intervalMs = 3000) {
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [creations, setCreations] = useState<Creation[]>([]);
  useEffect(() => {
    if (!client) return;
    let cancelled = false;
    const tick = () => {
      if (conversationId) {
        client
          .conversation(conversationId)
          .then((c) => !cancelled && setConversation(c))
          .catch(() => undefined);
      } else setConversation(null);
      if (isWorkflowsClient(client)) {
        client
          .recentCreations()
          .then((all) => !cancelled && setCreations(all))
          .catch(() => undefined);
      }
    };
    tick();
    const timer = window.setInterval(() => {
      if (!document.hidden) tick();
    }, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [client, conversationId, intervalMs]);
  return { conversation, creations };
}
