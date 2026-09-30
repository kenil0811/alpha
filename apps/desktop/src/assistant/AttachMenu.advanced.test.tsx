import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AttachMenu } from "./AttachMenu";
import type { AccessMode, ModelChoice } from "./advanced";

/** A minimal Settings/Models-accounts double: just enough for the Advanced submenu's Model
 *  group and its Settings -> Access default. */
function fakeClient() {
  return {
    listModelAccounts: vi.fn().mockResolvedValue([
      { id: "claude", label: "Claude", state: "connected", cli_present: true, signed_in: true, key_last4: null, dot: { color: "green", tooltip: "Connected" } },
      { id: "openrouter", label: "OpenRouter", state: "not_configured", cli_present: null, signed_in: null, key_last4: null, dot: { color: "grey", tooltip: "Not connected" } },
    ]),
    getSettings: vi.fn().mockResolvedValue([{ id: "access.mode", group: "Access", title: "", description: "", kind: "choice", options: [], minimum: null, maximum: null, unit: null, default: "ask", value: "ask" }]),
  };
}

function Harness({ onAccessModeChange, onModelChange, accessMode = "ask", model = null }: { onAccessModeChange: (m: AccessMode) => void; onModelChange: (m: ModelChoice | null) => void; accessMode?: AccessMode; model?: ModelChoice | null }) {
  return (
    <AttachMenu
      onAdd={() => undefined}
      advanced={{ accessMode, onAccessModeChange, model, onModelChange, client: fakeClient() }}
    />
  );
}

/** Radix's DropdownMenu.Sub opens reliably on keyboard nav in jsdom (no real pointer path for
 *  hover, so a plain click on a submenu item can miss - see AP-182 audit notes in the commit).
 *  ArrowRight opens the submenu from its trigger; the item is then just another menu item. */
async function openAdvanced(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Add files, folders, images or audio" }));
  const trigger = await screen.findByRole("menuitem", { name: /Advanced/ });
  trigger.focus();
  await user.keyboard("{ArrowRight}");
}

describe("the + menu's Advanced submenu", () => {
  it("lists the three Access options and reports a plain choice", async () => {
    const onAccessModeChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness onAccessModeChange={onAccessModeChange} onModelChange={vi.fn()} />);
    await openAdvanced(user);
    expect(await screen.findByRole("menuitem", { name: /Ask for approval/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Approve for me/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Full access/ })).toBeInTheDocument();
    (await screen.findByRole("menuitem", { name: /Approve for me/ })).focus();
    await user.keyboard("{Enter}");
    expect(onAccessModeChange).toHaveBeenCalledWith("approve_for_me");
  });

  it("choosing a model reports the account id", async () => {
    const onModelChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness onAccessModeChange={vi.fn()} onModelChange={onModelChange} />);
    await openAdvanced(user);
    (await screen.findByRole("menuitem", { name: /OpenRouter/ })).focus();
    await user.keyboard("{Enter}");
    expect(onModelChange).toHaveBeenCalledWith({ provider: "openrouter" });
  });

  it("choosing Full access asks once to confirm, and does nothing on cancel", async () => {
    const onAccessModeChange = vi.fn();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    const user = userEvent.setup();
    render(<Harness onAccessModeChange={onAccessModeChange} onModelChange={vi.fn()} />);
    await openAdvanced(user);
    (await screen.findByRole("menuitem", { name: /Full access/ })).focus();
    await user.keyboard("{Enter}");
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(onAccessModeChange).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("choosing Full access applies it once confirmed", async () => {
    const onAccessModeChange = vi.fn();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    render(<Harness onAccessModeChange={onAccessModeChange} onModelChange={vi.fn()} />);
    await openAdvanced(user);
    (await screen.findByRole("menuitem", { name: /Full access/ })).focus();
    await user.keyboard("{Enter}");
    expect(onAccessModeChange).toHaveBeenCalledWith("full");
    confirmSpy.mockRestore();
  });

  it("shows a small chip next to + only when a non-default choice is active", () => {
    const { rerender } = render(<Harness onAccessModeChange={vi.fn()} onModelChange={vi.fn()} accessMode="ask" />);
    expect(screen.queryByText(/Approve for me|Full access/)).not.toBeInTheDocument();
    rerender(<Harness onAccessModeChange={vi.fn()} onModelChange={vi.fn()} accessMode="approve_for_me" />);
    expect(screen.getByText("Approve for me")).toBeInTheDocument();
  });
});
