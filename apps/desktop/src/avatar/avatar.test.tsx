/** The avatar is on every surface, follows real state, opens the assistant, can be hidden in
 *  Settings, and holds still for reduced motion. */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { SettingField } from "../core/client";
import { fakeConnection } from "../test/fakeClient";
import { FakeWorkflowsClient, sampleDetail, sampleSummary } from "../test/fakeWorkflows";

const AVATAR_SETTING: SettingField = {
  id: "look.avatar",
  group: "Look",
  title: "Show the assistant's avatar",
  description: "A small panda in the corner of every page.",
  kind: "choice",
  options: [
    { value: "on", label: "Show" },
    { value: "off", label: "Hide" },
  ],
  minimum: null,
  maximum: null,
  unit: null,
  default: "on",
  value: "on",
};

function avatar(): HTMLElement {
  return document.querySelector<HTMLElement>("button.avatar")!;
}

beforeEach(() => {
  window.localStorage.clear();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the avatar", () => {
  it("is on every surface and opens the assistant from a module page", async () => {
    const client = new FakeWorkflowsClient();
    client.apps = [sampleSummary()];
    client.details.set("notes-list-1a2b3c", sampleDetail());
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByText("Runtime connected");
    await waitFor(() => expect(avatar()).toBeInTheDocument());
    expect(avatar()).toHaveAccessibleName("Assistant");
    expect(avatar()).toHaveAccessibleDescription("Ask me anything, or describe a tool you want");
    for (const place of ["Activity", "Settings", "Home"]) {
      await user.click(screen.getByRole("button", { name: place }));
      expect(avatar()).toBeInTheDocument();
    }
    await user.click(await screen.findByRole("button", { name: "Notes list" }));
    await screen.findByRole("heading", { name: "Notes list" });
    expect(screen.queryByRole("complementary", { name: "Assistant" })).not.toBeInTheDocument();
    expect(avatar()).not.toHaveClass("avatar--beside");
    await user.click(avatar());
    expect(await screen.findByRole("complementary", { name: "Assistant" })).toBeInTheDocument();
    expect(avatar()).toHaveClass("avatar--beside");
  });

  it("thinks while the assistant works on a request, even with the panel closed", async () => {
    const client = new FakeWorkflowsClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByText("Runtime connected");
    await user.type(screen.getByLabelText("What do you want done?"), "Track my reading");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(avatar()).toHaveAttribute("data-state", "thinking"));
    expect(avatar()).toHaveAccessibleDescription("Working out your request");
    await user.click(screen.getByRole("button", { name: "Hide assistant" }));
    expect(avatar()).toHaveAttribute("data-state", "thinking");
  });

  it("shows the disconnected state when Claude Code is signed out", async () => {
    const client = new FakeWorkflowsClient();
    client.connection = fakeConnection("signed_out");
    render(<App client={client} />);
    await waitFor(() => expect(avatar()).toHaveAttribute("data-state", "disconnected"));
    expect(avatar()).toHaveAccessibleDescription("Signed out of Claude Code");
  });

  it("is hidden and shown from Settings, and the choice is saved in Core", async () => {
    const client = new FakeWorkflowsClient();
    client.settingsFields = [...client.settingsFields, { ...AVATAR_SETTING, value: "off" }];
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByText("Runtime connected");
    await waitFor(() => expect(avatar()).toBeNull());
    await user.click(screen.getByRole("button", { name: "Settings" }));
    const look = await screen.findByLabelText("Look");
    await user.selectOptions(within(look).getByLabelText("Show the assistant's avatar"), "on");
    await waitFor(() => expect(client.settingsUpdates).toEqual([{ "look.avatar": "on" }]));
    await waitFor(() => expect(avatar()).toBeInTheDocument());
    await user.selectOptions(within(look).getByLabelText("Show the assistant's avatar"), "off");
    await waitFor(() => expect(avatar()).toBeNull());
  });

  it("holds still for reduced motion", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("reduce"),
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));
    render(<App client={new FakeWorkflowsClient()} />);
    await waitFor(() => expect(avatar()).toBeInTheDocument());
    // The static head, not the animated rig.
    expect(within(avatar()).getByRole("img", { hidden: true, name: "Zazoo" })).toBeInTheDocument();
    expect(within(avatar()).queryByRole("img", { hidden: true, name: "Zazoo, your companion" })).toBeNull();
  });
});
