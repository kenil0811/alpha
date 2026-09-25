/** F03.C02 controls: session binding, grants, malformed requests, revocation and expiry, over
 *  real MessagePorts. */
import { describe, expect, it, vi } from "vitest";
import { BridgeClient, BridgeRequestError } from "./client";
import { BridgeError, BridgeHost, type BridgeHandlers } from "./host";
import { PROTOCOL_VERSION, type BridgeSession } from "./protocol";

function session(id: string, actions: string[] = ["synthetic.echo"], views: string[] = []): BridgeSession {
  return {
    session_id: id,
    owner: { kind: "app", app_id: `app_${id}`, release_id: "rel_1" },
    grant: { actions, read_views: views },
    expires_at: new Date(Date.now() + 60_000).toISOString(),
  };
}

function pair(s: BridgeSession, handlers: BridgeHandlers = {}, now?: () => number) {
  const channel = new MessageChannel();
  const events: string[] = [];
  const host = new BridgeHost({ session: s, handlers, now, onEvent: (e) => events.push(`${e.kind}:${JSON.stringify(e.detail)}`) });
  host.bind(channel.port1);
  const client = BridgeClient.fromPort(channel.port2, s.session_id);
  return { host, client, channel, events };
}

const handlers: BridgeHandlers = {
  actionInvoke: async (_s, payload) => ({ operation_id: `op_${payload.action_id}_${JSON.stringify(payload.input).length}` }),
  operationObserve: async (_s, payload) => ({ operation_id: payload.operation_id, state: "succeeded" }),
};

describe("bridge session", () => {
  it("delivers grant on ready and answers a granted action", async () => {
    const { host, client } = pair(session("s1"), handlers);
    await client.whenReady();
    expect(client.grant).toEqual({ actions: ["synthetic.echo"], read_views: [] });
    const result = await client.request<{ operation_id: string }>("action.invoke", { action_id: "synthetic.echo", input: { text: "hi" } });
    expect(result.operation_id).toBe("op_synthetic.echo_13");
    const observed = await client.request<{ state: string }>("operation.observe", { operation_id: result.operation_id });
    expect(observed.state).toBe("succeeded");
    host.revoke("done");
  });

  it("refuses actions and views outside the grant without calling handlers", async () => {
    const invoke = vi.fn(handlers.actionInvoke!);
    const { client } = pair(session("s2", ["other.action"]), { ...handlers, actionInvoke: invoke });
    await client.whenReady();
    await expect(client.request("action.invoke", { action_id: "synthetic.echo", input: {} })).rejects.toMatchObject({ code: "forbidden" });
    await expect(client.request("records.query", { view: "items" })).rejects.toMatchObject({ code: "forbidden" });
    expect(invoke).not.toHaveBeenCalled();
  });

  it("cannot observe an operation created by another session", async () => {
    const a = pair(session("a"), handlers);
    const b = pair(session("b"), handlers);
    await Promise.all([a.client.whenReady(), b.client.whenReady()]);
    const created = await a.client.request<{ operation_id: string }>("action.invoke", { action_id: "synthetic.echo", input: {} });
    await expect(b.client.request("operation.observe", { operation_id: created.operation_id })).rejects.toMatchObject({ code: "forbidden" });
    expect((await a.client.request<{ state: string }>("operation.observe", { operation_id: created.operation_id })).state).toBe("succeeded");
  });

  it("rejects a message carrying another session's id on this port", async () => {
    const { channel, client } = pair(session("s3"), handlers);
    await client.whenReady();
    const reply = new Promise<unknown>((resolve) => {
      const previous = channel.port2.onmessage;
      channel.port2.onmessage = (event) => {
        resolve(event.data);
        channel.port2.onmessage = previous;
      };
    });
    channel.port2.postMessage({ protocol_version: PROTOCOL_VERSION, session_id: "s-other", request_id: "r1", type: "action.invoke", payload: { action_id: "synthetic.echo", input: {} } });
    expect(await reply).toMatchObject({ type: "error", request_id: "r1", error: { code: "unknown_session" } });
  });

  it("rejects malformed requests with typed errors", async () => {
    const { channel, client } = pair(session("s4"), handlers);
    await client.whenReady();
    const replies: unknown[] = [];
    const gotAll = new Promise<void>((resolve) => {
      channel.port2.onmessage = (event) => {
        replies.push(event.data);
        if (replies.length === 6) resolve();
      };
    });
    const base = { protocol_version: PROTOCOL_VERSION, session_id: "s4", request_id: "x", type: "action.invoke", payload: { action_id: "synthetic.echo", input: {} } };
    channel.port2.postMessage("not an object");
    channel.port2.postMessage({ ...base, protocol_version: "0.1" });
    channel.port2.postMessage({ ...base, request_id: "" });
    channel.port2.postMessage({ ...base, type: "shell.exec" });
    channel.port2.postMessage({ ...base, payload: "rm -rf" });
    channel.port2.postMessage({ ...base, grants: ["all"] });
    await gotAll;
    for (const reply of replies) expect(reply).toMatchObject({ type: "error", error: { code: "invalid_request" } });
    expect((replies[2] as { request_id: string }).request_id).toBe("");
  });

  it("unsupported request types are refused explicitly", async () => {
    const { client } = pair(session("s5", ["a"], ["v"]), { actionInvoke: handlers.actionInvoke });
    await client.whenReady();
    await expect(client.request("artifact.open", { artifact_id: "x" })).rejects.toMatchObject({ code: "unsupported" });
    await expect(client.request("shell.navigate", { destination: "settings" })).rejects.toMatchObject({ code: "unsupported" });
    await expect(client.request("records.query", { view: "v" })).rejects.toMatchObject({ code: "unsupported" });
  });

  it("revocation notifies the client, fails pending work and silences the old port", async () => {
    const gate: { release: (() => void) | null } = { release: null };
    const slow: BridgeHandlers = {
      actionInvoke: () => new Promise((resolve) => {
        gate.release = () => resolve({ operation_id: "late" });
      }),
    };
    const { host, client, channel, events } = pair(session("s6"), slow);
    await client.whenReady();
    const revokedReason = new Promise<string>((resolve) => client.onRevoked(resolve));
    const pending = client.request("action.invoke", { action_id: "synthetic.echo", input: {} });
    await new Promise((r) => setTimeout(r, 10));
    host.revoke("navigation");
    expect(await revokedReason).toBe("navigation");
    await expect(pending).rejects.toMatchObject({ code: "revoked" });
    gate.release?.();
    await expect(client.request("action.invoke", { action_id: "synthetic.echo", input: {} })).rejects.toMatchObject({ code: "revoked" });
    // A client that ignores the revocation and keeps the raw port gets nothing back.
    let answered = false;
    channel.port2.onmessage = () => {
      answered = true;
    };
    channel.port2.postMessage({ protocol_version: PROTOCOL_VERSION, session_id: "s6", request_id: "zombie", type: "action.invoke", payload: { action_id: "synthetic.echo", input: {} } });
    await new Promise((r) => setTimeout(r, 50));
    expect(answered).toBe(false);
    expect(events.some((e) => e.startsWith("revoked:"))).toBe(true);
  });

  it("an expired session is revoked on its next request", async () => {
    let clock = Date.now();
    const s = session("s7");
    const { client, host } = pair(s, handlers, () => clock);
    await client.whenReady();
    clock = Date.parse(s.expires_at) + 1;
    await expect(client.request("action.invoke", { action_id: "synthetic.echo", input: {} })).rejects.toMatchObject({ code: "revoked" });
    expect(host.isRevoked).toBe(true);
  });

  it("handler failures are reported without internals", async () => {
    const { client } = pair(session("s8"), {
      actionInvoke: async () => {
        throw new Error("sqlite path /Users/x/control.sqlite locked");
      },
    });
    await client.whenReady();
    const error = (await client
      .request("action.invoke", { action_id: "synthetic.echo", input: {} })
      .catch((e: unknown) => e)) as BridgeRequestError;
    expect(error).toBeInstanceOf(BridgeRequestError);
    expect(error.code).toBe("internal");
    expect(error.message).not.toContain("sqlite");
    const typed = pair(session("s9"), {
      actionInvoke: async () => {
        throw new BridgeError("not_found", "no such thing", "try again later");
      },
    });
    await typed.client.whenReady();
    await expect(typed.client.request("action.invoke", { action_id: "synthetic.echo", input: {} })).rejects.toMatchObject({ code: "not_found", recovery: "try again later" });
  });

  it("forwards only granted views with a validated query shape", async () => {
    const seen: unknown[] = [];
    const { client } = pair(session("s11", [], ["entries.list"]), {
      recordsQuery: async (_s, payload) => {
        seen.push(payload);
        return { records: [], next_cursor: null };
      },
    });
    await client.whenReady();
    const where = { all: [{ field: "kind", op: "eq", value: "task" }] };
    await client.request("records.query", { view: "entries.list", where, order_by: [{ field: "title", direction: "desc" }], limit: 20, cursor: "c1" });
    expect(seen).toEqual([{ view: "entries.list", where, order_by: [{ field: "title", direction: "desc" }], limit: 20, cursor: "c1" }]);
    await expect(client.request("records.query", { view: "entries.secret" })).rejects.toMatchObject({ code: "forbidden" });
    for (const bad of [
      { view: "entries.list", sql: "select 1" },
      { view: "entries.list", where: "1=1" },
      { view: "entries.list", limit: 5000 },
      { view: "entries.list", limit: 2.5 },
      { view: "entries.list", order_by: [{ field: "x", direction: "sideways" }] },
      { view: "entries.list", collection: "other" },
    ]) {
      await expect(client.request("records.query", bad)).rejects.toMatchObject({ code: "invalid_request" });
    }
    expect(seen).toHaveLength(1);
  });

  it("throttles when too many requests are in flight", async () => {
    const blockers: Array<() => void> = [];
    const { client } = pair(session("s10"), {
      actionInvoke: () => new Promise((resolve) => blockers.push(() => resolve({ operation_id: "x" }))),
    });
    await client.whenReady();
    const first = Array.from({ length: 16 }, () => client.request("action.invoke", { action_id: "synthetic.echo", input: {} }));
    await new Promise((r) => setTimeout(r, 10));
    await expect(client.request("action.invoke", { action_id: "synthetic.echo", input: {} })).rejects.toMatchObject({ code: "throttled" });
    blockers.forEach((b) => b());
    await Promise.all(first);
  });
});
