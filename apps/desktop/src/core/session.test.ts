import { describe, expect, it } from "vitest";
import { parseSession } from "./session";

describe("parseSession", () => {
  const token = "t".repeat(64);

  it("accepts the host's camelCase loopback session", () => {
    expect(parseSession({ baseUrl: "http://127.0.0.1:64719", token })).toEqual({
      baseUrl: "http://127.0.0.1:64719",
      token,
    });
  });

  it("rejects a snake_case or non-loopback answer precisely", () => {
    expect(() => parseSession({ base_url: "http://127.0.0.1:1", token })).toThrow(/invalid core session/);
    expect(() => parseSession({ baseUrl: "http://example.com:1", token })).toThrow(/invalid core session/);
    expect(() => parseSession({ baseUrl: "http://127.0.0.1:1", token: "short" })).toThrow(/invalid core session/);
    expect(() => parseSession(null)).toThrow(/invalid core session/);
  });
});
