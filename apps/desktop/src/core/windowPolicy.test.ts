/**
 * The native window's content security policy must allow what the shell itself loads. Found in
 * M1-R07: preview images are loaded as blob: URLs (client.imageUrl), the policy allowed only
 * 'self' and data:, and the ready card showed empty boxes in the Alpha window. The browser
 * shell tests could not see it, since the policy applies only in the native host.
 */
import { describe, expect, it } from "vitest";
import tauri from "../../src-tauri/tauri.conf.json";

function directive(name: string): string[] {
  const found = tauri.app.security.csp
    .split(";")
    .map((part) => part.trim().split(/\s+/))
    .find(([head]) => head === name);
  return found ? found.slice(1) : [];
}

describe("the Alpha window's content security policy", () => {
  it("shows images the shell loads as blob: URLs, and nothing from elsewhere", () => {
    expect(directive("img-src")).toEqual(["'self'", "data:", "blob:"]);
  });

  it("frames only generated screens", () => {
    expect(directive("frame-src")).toEqual(["alpha-ui:"]);
  });
});
