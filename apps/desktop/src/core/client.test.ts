import { describe, expect, it } from "vitest";
import { HttpCoreClient, parseSseChunk } from "./client";

describe("parseSseChunk", () => {
  it("emits complete frames and keeps the remainder", () => {
    const frames: { id?: string; event?: string; data: string }[] = [];
    const rest = parseSseChunk(
      ": connected\n\nid: 7\nevent: run_event\ndata: {\"a\":1}\n\nid: 8\nevent: run_ev",
      (f) => frames.push(f),
    );
    expect(frames).toEqual([{ id: "7", event: "run_event", data: '{"a":1}' }]);
    expect(rest).toBe("id: 8\nevent: run_ev");
  });
});

describe("HttpCoreClient", () => {
  it("sends the bearer credential and surfaces typed errors", async () => {
    const seen: { url: string; headers: Record<string, string> }[] = [];
    const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
      seen.push({ url: String(input), headers: (init?.headers ?? {}) as Record<string, string> });
      return new Response(JSON.stringify({ error: "unauthorized" }), { status: 401 });
    }) as typeof fetch;
    const client = new HttpCoreClient({ baseUrl: "http://127.0.0.1:1", token: "t".repeat(32) }, fetchImpl);
    await expect(client.health()).rejects.toMatchObject({ status: 401, message: "unauthorized" });
    expect(seen[0].url).toBe("http://127.0.0.1:1/api/health");
    expect(seen[0].headers.Authorization).toBe(`Bearer ${"t".repeat(32)}`);
  });

  it("gives up on a request a stalled Core never answers, so polling can report it", async () => {
    // Core accepts the connection but never replies: only the request's own limit ends it.
    const fetchImpl = ((_input: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(init.signal!.reason));
      })) as typeof fetch;
    const client = new HttpCoreClient({ baseUrl: "http://127.0.0.1:1", token: "t".repeat(32) }, fetchImpl, 50);
    await expect(client.creation("create_1")).rejects.toMatchObject({
      status: 0,
      code: "timeout",
      message: "Alpha's runtime did not answer in time.",
    });
  }, 2_000);
});
