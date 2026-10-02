/** The panel-control reducer: collapse/expand/extend, width clamping, and stepped Escape. */
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { usePanelControl } from "./panel";

beforeEach(() => {
  window.localStorage.clear();
});

function setup(overrides: Partial<Parameters<typeof usePanelControl>[0]> = {}) {
  return renderHook(() =>
    usePanelControl({
      defaultWidth: 220,
      minWidth: 76,
      maxWidth: 360,
      storageKeyWidth: "test.width",
      storageKeyCollapsed: "test.collapsed",
      snap: true,
      snapMidpoint: 148,
      ...overrides,
    }),
  );
}

describe("usePanelControl", () => {
  it("starts expanded at the default width", () => {
    const { result } = setup();
    expect(result.current.mode).toBe("expanded");
    expect(result.current.width).toBe(220);
  });

  it("resizeBy widens into extended mode, clamped to maxWidth", () => {
    const { result } = setup();
    act(() => result.current.resizeBy(200));
    expect(result.current.mode).toBe("extended");
    expect(result.current.width).toBe(360);
  });

  it("Escape steps extended -> expanded -> collapsed, one level at a time", () => {
    const { result } = setup();
    act(() => result.current.resizeBy(100));
    expect(result.current.mode).toBe("extended");

    act(() => {
      const handled = result.current.handleEscape();
      expect(handled).toBe(true);
    });
    expect(result.current.mode).toBe("expanded");

    act(() => {
      const handled = result.current.handleEscape();
      expect(handled).toBe(true);
    });
    expect(result.current.mode).toBe("collapsed");

    act(() => {
      const handled = result.current.handleEscape();
      expect(handled).toBe(false);
    });
    expect(result.current.mode).toBe("collapsed");
  });

  it("persists width and collapsed state across remount", () => {
    const { result, unmount } = setup();
    act(() => result.current.setCollapsed(true));
    unmount();
    const { result: second } = setup();
    expect(second.current.collapsed).toBe(true);
  });

  it("migrates a legacy localStorage key on first read", () => {
    window.localStorage.setItem("legacy.collapsed", "1");
    const { result } = setup({ migrateCollapsedKeys: ["legacy.collapsed"] });
    expect(result.current.collapsed).toBe(true);
  });
});
