import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
  // The app now routes through HashRouter (real window.location.hash); jsdom's location
  // persists across tests in the same file unlike component state, so every test needs to
  // start at "/" the way it did before routing existed.
  window.location.hash = "";
});

// jsdom has no ResizeObserver; Radix's Popover/Select/Tooltip primitives use it to
// measure content, so every test importing them needs at least a no-op stub.
if (typeof window.ResizeObserver === "undefined") {
  window.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
