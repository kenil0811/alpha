/** Push-to-talk shortcut: persists across reads, and the Settings row degrades honestly when
 *  there is no host (web preview) to watch for it. */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { FakeWorkflowsClient } from "../test/fakeWorkflows";
import { keycodeFor, readShortcut, shortcutLabel, writeShortcut } from "./ptt";

beforeEach(() => {
  window.localStorage.clear();
});

describe("the push-to-talk shortcut", () => {
  it("defaults to Fn and round-trips a recorded key through storage", () => {
    expect(readShortcut()).toEqual({ mode: "fn" });
    writeShortcut({ mode: "key", code: 0x31, shift: true, control: false, alt: true, command: false, label: "Space" });
    expect(readShortcut()).toEqual({ mode: "key", code: 0x31, shift: true, control: false, alt: true, command: false, label: "Space" });
    expect(shortcutLabel(readShortcut())).toBe("⌥⇧Space");
  });

  it("maps a physical key to its macOS keycode, and leaves modifiers unmapped", () => {
    expect(keycodeFor("Space")).toBe(0x31);
    expect(keycodeFor("ShiftLeft")).toBeNull();
  });

  it("tells the person push-to-talk needs the desktop app when there is no Tauri host", async () => {
    const user = userEvent.setup();
    render(<App client={new FakeWorkflowsClient()} />);
    expect(await screen.findByText("Runtime connected")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Settings" }));
    await user.click(screen.getByRole("button", { name: "Desktop" }));
    const row = await screen.findByLabelText("Push to talk");
    expect(row).toHaveTextContent("Desktop app only");
  });
});
