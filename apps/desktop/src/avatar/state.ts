/**
 * What the avatar shows, derived only from what Alpha really knows: the conversation in front of
 * the person, the creations Core reports, the runs on the event stream and the Claude
 * connection. Nothing here is stored or invented; the avatar is a rendering of this state.
 */
import type { Run } from "@alpha/contracts";
import { CREATION_DONE, type Conversation, type Creation, type ModelConnection } from "../core/client";
import type { ZazooPerformance } from "./zazoo/director";
import { connectionSummary, isDisconnected } from "../shell/models";

export type AvatarState = "disconnected" | "error" | "awaiting" | "building" | "thinking" | "working" | "idle";

export interface AvatarSignals {
  /** The conversation the assistant panel has selected (null for a new request). */
  conversation: Conversation | null;
  /** Recent creations, newest first. */
  creations: Creation[];
  runs: Run[];
  connection: ModelConnection | null;
}

export interface AvatarView {
  state: AvatarState;
  /** One plain sentence: what the avatar is showing and why. */
  text: string;
}

/** A failed module run is shown for this long, then the avatar lets it go (Activity keeps it). */
export const RUN_FAILURE_SHOWN_MS = 15 * 60 * 1000;

const WAITING_RUN = new Set(["waiting_input", "waiting_approval", "waiting_connection"]);
const ACTIVE_RUN = new Set(["queued", "running"]);

/** Most pressing first: a broken connection blocks everything, then a failure the person should
 *  see, then something waiting on them, then work in progress. */
export function avatarView({ conversation, creations, runs, connection }: AvatarSignals, now = Date.now()): AvatarView {
  if (connection && isDisconnected(connection)) return { state: "disconnected", text: connectionSummary(connection).headline };

  const own = conversation ? creations.find((c) => c.conversation_id === conversation.conversation_id) ?? null : null;
  if (conversation?.state === "failed") return { state: "error", text: "Your last request didn't work out" };
  if (own?.state === "failed") return { state: "error", text: `Making ${own.app_name ?? "your module"} didn't work out` };
  const newestRun = [...runs].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  if (newestRun?.state === "failed" && now - new Date(newestRun.finished_at ?? newestRun.updated_at).getTime() < RUN_FAILURE_SHOWN_MS) {
    return { state: "error", text: "A module run failed. Activity has the reason" };
  }

  if (conversation?.state === "waiting_for_user") return { state: "awaiting", text: "Waiting for your answers" };
  // A plan for a new module waits for the person to press Create it (a change starts by itself).
  if (conversation?.state === "briefed" && conversation.delivery === "app" && !conversation.change_of && !conversation.quick_change && own === null) {
    return { state: "awaiting", text: "The plan is ready. Press Create it when it looks right" };
  }
  if (runs.some((r) => WAITING_RUN.has(r.state))) return { state: "awaiting", text: "A module run is waiting for you" };

  const making = creations.find((c) => !CREATION_DONE.has(c.state));
  if (making) return { state: "building", text: `${making.change_of ? "Changing" : "Making"} ${making.app_name ?? "your module"}` };
  if (conversation?.state === "thinking") return { state: "thinking", text: "Working out your request" };
  const active = runs.filter((r) => ACTIVE_RUN.has(r.state)).length;
  if (active) return { state: "working", text: active === 1 ? "A module is running" : `${active} modules are running` };
  return { state: "idle", text: "Ask me anything, or describe a tool you want" };
}

/** How each state is performed by the Zazoo rig (ported from Bridge's status-performance map). */
export const PERFORMANCE: Record<AvatarState, ZazooPerformance> = {
  idle: { emotion: "calm", action: "idle", warmth: 0.7, confidence: 0.7, energy: 0.35, attention: "cursor" },
  thinking: { emotion: "thinking", action: "idle", energy: 0.4, confidence: 0.6, attention: "away" },
  building: { emotion: "curious", action: "idle", energy: 0.6, attention: "away" },
  working: { emotion: "curious", action: "idle", energy: 0.5, attention: "away" },
  awaiting: { emotion: "unsure", action: "idle", warmth: 0.95, confidence: 0.45, energy: 0.3, attention: "user" },
  error: { emotion: "concerned", action: "idle", confidence: 0.4, energy: 0.3, attention: "user" },
  disconnected: { emotion: "sleepy", action: "idle", energy: 0.15, warmth: 0.6, attention: "user" },
};

/** One-shot when work lands without a problem: auto-reverts to the state's own pose. */
export const DONE_PERFORMANCE: ZazooPerformance = { emotion: "happy", warmth: 0.9, energy: 0.6, duration: 2.5 };
