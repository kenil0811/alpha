import { BridgeError } from "@alpha/ui-bridge";
import type { Run, RunEvent } from "@alpha/contracts";
import { describe, expect, it } from "vitest";
import { CoreError, outcomeFromEvents } from "../core/client";
import { FakeWorkflowsClient, sampleDetail } from "../test/fakeWorkflows";
import { appBridgeHandlers, appSession, appSessionRenewer } from "./appBridge";

describe("an App's UI session", () => {
  it("grants only the views and UI actions the App declared, owned by its current release", () => {
    const detail = sampleDetail({
      release_id: "rel_9",
      ui: { entry: "ui/src/main.tsx", views: [{ id: "recent_notes" } as never], actions: ["add_note"] },
    });
    const session = appSession(detail, 5);
    expect(session.owner).toEqual({ kind: "app", app_id: "notes-list-1a2b3c", release_id: "rel_9" });
    expect(session.grant).toEqual({ actions: ["add_note"], read_views: ["recent_notes"] });
    expect(session.session_id).toMatch(/^sess_[0-9a-f]{16}$/);
    const minutes = (Date.parse(session.expires_at) - Date.now()) / 60_000;
    expect(minutes).toBeGreaterThan(4.9);
    expect(minutes).toBeLessThanOrEqual(5);
  });

  it("grants nothing to an App without a declared screen", () => {
    expect(appSession(sampleDetail({ ui: null })).grant).toEqual({ actions: [], read_views: [] });
  });
});

describe("answering bridge requests", () => {
  const session = appSession(sampleDetail());

  it("invokes actions for this App only and reports the operation", async () => {
    const client = new FakeWorkflowsClient();
    const handlers = appBridgeHandlers(client, "notes-list-1a2b3c");
    const started = await handlers.actionInvoke!(session, { action_id: "add_note", input: { title: "a" } } as never);
    expect(started).toEqual({ operation_id: "run_1" });
    expect(client.invocations).toEqual([{ appId: "notes-list-1a2b3c", actionId: "add_note", input: { title: "a" }, origin: "ui" }]);
    const outcome = await handlers.operationObserve!(session, { operation_id: "run_1" } as never);
    expect(outcome).toMatchObject({ state: "succeeded", output: { id: "rec_1", revision: 1 } });
  });

  it("maps Core refusals to bridge errors without leaking detail", async () => {
    const client = new FakeWorkflowsClient();
    const handlers = appBridgeHandlers(client, "notes");
    const cases: [unknown, string, string | undefined][] = [
      [new CoreError("view not granted", 403), "forbidden", undefined],
      [new CoreError("bad input", 422), "invalid_request", undefined],
      [new CoreError("no such app", 404), "not_found", undefined],
      [new CoreError("worker unavailable", 503), "unsupported", "Try again in a moment."],
      [new CoreError("boom", 500), "internal", "Try again in a moment."],
      [new TypeError("fetch failed: 127.0.0.1:53211"), "internal", undefined],
    ];
    for (const [error, code, recovery] of cases) {
      client.queryView = async () => {
        throw error;
      };
      const refused = await handlers.recordsQuery!(session, { view: "recent_notes" } as never).catch((e: unknown) => e);
      expect(refused).toBeInstanceOf(BridgeError);
      expect((refused as BridgeError).code).toBe(code);
      expect((refused as BridgeError).recovery).toBe(recovery);
      expect((refused as BridgeError).message).not.toContain("127.0.0.1");
    }
  });

  it("passes the view query through without the view id", async () => {
    const client = new FakeWorkflowsClient();
    const seen: unknown[] = [];
    client.queryView = async (...args: unknown[]) => {
      seen.push(args);
      return { records: [] };
    };
    await appBridgeHandlers(client, "notes").recordsQuery!(session, { view: "recent_notes", limit: 5 } as never);
    expect(seen).toEqual([["notes", "recent_notes", { limit: 5 }]]);
  });
});

describe("a finished run's outcome", () => {
  const run = (state: Run["state"], terminal_reason: string | null = null, output: Record<string, unknown> | null = null) =>
    ({ run_id: "run_1", state, terminal_reason, output }) as Run;
  const event = (kind: string, payload: Record<string, unknown>) => ({ kind, payload }) as RunEvent;

  it("reports output only for a success", () => {
    expect(outcomeFromEvents(run("succeeded", null, { total: 3 }), [])).toEqual({
      operation_id: "run_1",
      state: "succeeded",
      output: { total: 3 },
      error: null,
    });
  });

  it("prefers the worker's own plain message, then the contract problem, then the reason", () => {
    const workerError = event("worker.error", { message: "The food is needed.", operation_code: "input_invalid" });
    expect(outcomeFromEvents(run("failed", "worker_error"), [workerError]).error).toEqual({ code: "input_invalid", message: "The food is needed." });
    const contract = event("run.failed", { problem: "missing field 'id'" });
    expect(outcomeFromEvents(run("failed", "output_invalid"), [contract]).error).toEqual({
      code: "output_invalid",
      message: "The result did not match what the action promises: missing field 'id'",
    });
    expect(outcomeFromEvents(run("cancelled", "cancelled_by_user"), []).error).toEqual({ code: "cancelled_by_user", message: "cancelled_by_user" });
    expect(outcomeFromEvents(run("interrupted"), []).error).toEqual({ code: "interrupted", message: "The action interrupted." });
  });
});

describe("renewing an open screen's session", () => {
  const base = sampleDetail({
    release_id: "rel_9",
    ui: { entry: "ui/src/main.tsx", views: [{ id: "recent_notes" } as never], actions: ["add_note"] },
  });

  it("renews while the release and grant are unchanged", async () => {
    const client = new FakeWorkflowsClient();
    client.details.set(base.app_id, base);
    const renew = appSessionRenewer(client, base.app_id, 30);
    const outcome = await renew(appSession(base));
    expect("expires_at" in outcome).toBe(true);
    const minutes = (Date.parse((outcome as { expires_at: string }).expires_at) - Date.now()) / 60_000;
    expect(minutes).toBeGreaterThan(29);
  });

  it("ends the session when the App's release or grant changed", async () => {
    const client = new FakeWorkflowsClient();
    const session = appSession(base);
    client.details.set(base.app_id, { ...base, release_id: "rel_10" });
    expect(await appSessionRenewer(client, base.app_id)(session)).toEqual({ revoke: "release_changed" });
    client.details.set(base.app_id, { ...base, ui: { entry: "ui/src/main.tsx", views: [], actions: ["add_note", "delete_note"] } });
    expect(await appSessionRenewer(client, base.app_id)(session)).toEqual({ revoke: "grant_changed" });
  });

  it("lets a failed check surface so the session is kept", async () => {
    const client = new FakeWorkflowsClient();
    await expect(appSessionRenewer(client, "missing")(appSession(base))).rejects.toThrow();
  });
});
