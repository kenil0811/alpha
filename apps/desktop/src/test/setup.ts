import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

// findBy*/waitFor default to 1s; whole-app tests under full-suite contention need longer.
configure({ asyncUtilTimeout: 5000 });

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

// jsdom's own object-URL support chokes on a plain `new File(...)` (it expects internals only a
// real browser or its own Blob sets up); an attached image's chip thumbnail
// (assistant/attachments.ts) asks for one, so every test that pastes or drops an image needs a
// stub that just works.
URL.createObjectURL = () => "blob:stub";
URL.revokeObjectURL = () => undefined;
