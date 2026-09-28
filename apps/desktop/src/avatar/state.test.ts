/** The avatar shows only real state, most pressing first. */
import type { Run } from "@alpha/contracts";
import { describe, expect, it } from "vitest";
import type { Conversation, Creation } from "../core/client";
import { fakeConnection } from "../test/fakeClient";
import { avatarView, PERFORMANCE, RUN_FAILURE_SHOWN_MS, type AvatarSignals } from "./state";

const NOW = Date.parse("2026-09-27T12:00:00Z");

function conversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    conversation_id: "conv_1",
    state: "thinking",
    route_id: "claude-code-cli",
    created_at: "2026-09-27T11:59:00Z",
    updated_at: "2026-09-27T11:59:00Z",
    turns: [],
    current_brief: null,
    interpretation: null,
    questions: [],
    reply: null,
    delivery: null,
    error: null,
    ...overrides,
  };
}

function creation(overrides: Partial<Creation> = {}): Creation {
  return {
    creation_id: "cre_1",
    conversation_id: "conv_1",
    brief_id: "b",
    brief_revision: 1,
    app_id: "diet",
    app_name: "Diet log",
    state: "building",
    stage: "building",
    label: "Building",
    detail: null,
    progress: {},
    result: null,
    failure: null,
    history: [],
    created_at: "2026-09-27T11:59:00Z",
    updated_at: "2026-09-27T11:59:00Z",
    ...overrides,
  };
}

function run(state: Run["state"], at = "2026-09-27T11:58:00Z"): Run {
  return { run_id: `run_${state}`, state, created_at: at, updated_at: at, finished_at: at, origin: "ui", workspace_id: "w" } as unknown as Run;
}

const nothing: AvatarSignals = { conversation: null, creations: [], runs: [], connection: fakeConnection("connected") };
const view = (s: Partial<AvatarSignals>) => avatarView({ ...nothing, ...s }, NOW);

describe("avatar state", () => {
  it("is idle when nothing is going on", () => {
    expect(view({})).toEqual({ state: "idle", text: "Ask me anything, or describe a tool you want" });
    expect(view({ connection: null }).state).toBe("idle");
    expect(view({ connection: fakeConnection("not_used") }).state).toBe("idle");
  });

  it("thinks while a turn is in flight", () => {
    expect(view({ conversation: conversation() })).toEqual({ state: "thinking", text: "Working out your request" });
  });

  it("is building while a creation or change runs", () => {
    expect(view({ creations: [creation()] })).toEqual({ state: "building", text: "Making Diet log" });
    expect(view({ creations: [creation({ change_of: "diet" })] }).text).toBe("Changing Diet log");
    expect(view({ creations: [creation({ state: "active" })] }).state).toBe("idle");
  });

  it("waits for the person: questions, a plan to create, a run asking for input", () => {
    expect(view({ conversation: conversation({ state: "waiting_for_user" }) }).state).toBe("awaiting");
    const plan = conversation({ state: "briefed", delivery: "app" });
    expect(view({ conversation: plan })).toEqual({ state: "awaiting", text: "The plan is ready. Press Create it when it looks right" });
    expect(view({ conversation: plan, creations: [creation()] }).state).toBe("building");
    expect(view({ conversation: { ...plan, change_of: "diet" } }).state).toBe("idle");
    expect(view({ runs: [run("waiting_input")] }).state).toBe("awaiting");
  });

  it("shows an error for a failed turn, creation or recent run", () => {
    expect(view({ conversation: conversation({ state: "failed", error: "x" }) }).state).toBe("error");
    expect(view({ conversation: conversation({ state: "briefed" }), creations: [creation({ state: "failed" })] }).text).toBe("Making Diet log didn't work out");
    expect(view({ runs: [run("failed")] }).state).toBe("error");
    const old = new Date(NOW - RUN_FAILURE_SHOWN_MS - 1000).toISOString();
    expect(view({ runs: [run("failed", old)] }).state).toBe("idle");
    expect(view({ runs: [run("failed"), run("succeeded", "2026-09-27T11:59:30Z")] }).state).toBe("idle");
  });

  it("works while a module runs", () => {
    expect(view({ runs: [run("running")] })).toEqual({ state: "working", text: "A module is running" });
  });

  it("puts a broken connection first, with its plain reason", () => {
    for (const status of ["signed_out", "cli_missing", "cli_too_old"] as const) {
      expect(view({ conversation: conversation(), connection: fakeConnection(status) }).state).toBe("disconnected");
    }
    expect(view({ connection: fakeConnection("signed_out") }).text).toBe("Signed out of Claude Code");
    expect(view({ connection: fakeConnection("last_call_failed") }).state).toBe("idle");
  });

  it("errors outrank waiting, and waiting outranks work", () => {
    expect(view({ conversation: conversation({ state: "failed" }), creations: [creation({ conversation_id: "other" })] }).state).toBe("error");
    expect(view({ conversation: conversation({ state: "waiting_for_user" }), creations: [creation({ conversation_id: "other" })] }).state).toBe("awaiting");
  });

  it("has a performance for every state", () => {
    for (const state of ["disconnected", "error", "awaiting", "building", "thinking", "working", "idle"] as const) {
      expect(PERFORMANCE[state].emotion).toBeTruthy();
    }
  });
});
