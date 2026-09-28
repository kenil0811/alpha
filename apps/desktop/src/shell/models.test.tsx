/** Settings -> Models says whether Claude is reachable and how to fix it; a failed turn caused by
 *  the connection says so in the assistant panel; replies can be read aloud. */
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { Conversation } from "../core/client";
import { fakeConnection } from "../test/fakeClient";
import { FakeWorkflowsClient } from "../test/fakeWorkflows";

beforeEach(() => {
  window.localStorage.clear();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

async function openModels(client: FakeWorkflowsClient) {
  const user = userEvent.setup();
  render(<App client={client} />);
  await screen.findByText("Runtime connected");
  await user.click(screen.getByRole("button", { name: "Settings" }));
  return { user, card: await screen.findByLabelText("Connection to Claude") };
}

describe("Settings -> Models connection", () => {
  it("shows a working connection with version, account and last call, and checks on demand", async () => {
    const client = new FakeWorkflowsClient();
    const { user, card } = await openModels(client);
    expect(within(card).getByRole("status")).toHaveTextContent("Connected");
    expect(card).toHaveTextContent("2.1.283");
    expect(card).toHaveTextContent("person@example.com · max plan");
    expect(card).toHaveTextContent(/2 min ago · took 7\.4 s/);
    expect(within(card).queryByRole("button", { name: "Sign in" })).toBeNull();
    await user.click(within(card).getByRole("button", { name: "Check now" }));
    expect(await within(card).findByText("A small call worked (0.9 s).")).toBeInTheDocument();
    expect(client.connectionChecks).toBe(1);
  });

  it.each([
    ["cli_missing", "Claude Code is not installed on this Mac", "Install Claude Code"],
    ["cli_too_old", "Claude Code 2.1.223 is too old (Alpha needs 2.1.283 or newer)", "claude update"],
    ["last_call_failed", "Last call failed: the model took too long to answer", "Press Check now"],
  ] as const)("%s: says what is wrong and the fix", async (status, headline, fix) => {
    const client = new FakeWorkflowsClient();
    client.connection = fakeConnection(status);
    const { card } = await openModels(client);
    await waitFor(() => expect(within(card).getByRole("status")).toHaveTextContent(headline));
    expect(card).toHaveTextContent(fix);
    expect(within(card).getByText("Needs attention")).toBeInTheDocument();
  });

  it("signed out: Sign in starts the CLI's browser sign-in and waits for it", async () => {
    const client = new FakeWorkflowsClient();
    client.connection = fakeConnection("signed_out");
    const { user, card } = await openModels(client);
    expect(within(card).getByRole("status")).toHaveTextContent("Signed out of Claude Code");
    await user.click(within(card).getByRole("button", { name: "Sign in" }));
    expect(client.signIns).toBe(1);
    expect(await within(card).findByText(/A browser window has opened/)).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Waiting for sign-in…" })).toBeDisabled();
  });
});

function failedTurn(client: FakeWorkflowsClient) {
  client.assistantScript = (c: Conversation) => ({ ...c, state: "failed", error: "Alpha's model service is not signed in" });
}

describe("a failed turn caused by the connection", () => {
  it("says so plainly and links to Settings -> Models", async () => {
    const client = new FakeWorkflowsClient();
    client.connection = fakeConnection("signed_out");
    failedTurn(client);
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByText("Runtime connected");
    await user.type(screen.getByLabelText("What do you want done?"), "Track my reading");
    await user.click(screen.getByRole("button", { name: "Send" }));
    const problem = await screen.findByRole("alert", { name: "Alpha cannot reach Claude" });
    expect(problem).toHaveTextContent("Alpha could not reach Claude: Signed out of Claude Code.");
    expect(problem).toHaveTextContent("claude auth login");
    await user.click(within(problem).getByRole("button", { name: "Open Settings → Models" }));
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByLabelText("Connection to Claude")).toBeInTheDocument();
  });

  it("keeps the usual message when the connection is fine", async () => {
    const client = new FakeWorkflowsClient();
    client.assistantScript = (c: Conversation) => ({ ...c, state: "failed", error: "the model's answer was incomplete" });
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByText("Runtime connected");
    await user.type(screen.getByLabelText("What do you want done?"), "Track my reading");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Alpha could not work this out: the model's answer was incomplete.");
    expect(screen.queryByRole("button", { name: "Open Settings → Models" })).toBeNull();
  });
});

describe("reading replies aloud", () => {
  it("speaks a reply that arrives, only when switched on", async () => {
    const spoken: string[] = [];
    vi.stubGlobal("speechSynthesis", { cancel: () => undefined, speak: (u: { text: string }) => spoken.push(u.text) });
    vi.stubGlobal(
      "SpeechSynthesisUtterance",
      class {
        constructor(public text: string) {}
      },
    );
    const client = new FakeWorkflowsClient();
    client.settingsFields = [
      ...client.settingsFields,
      { id: "voice.speak_replies", group: "Voice", title: "Read replies aloud", description: "", kind: "choice", options: [{ value: "off", label: "Off" }, { value: "on", label: "On" }], minimum: null, maximum: null, unit: null, default: "off", value: "on" },
    ];
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByText("Runtime connected");
    await user.type(screen.getByLabelText("What do you want done?"), "What can you do?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    const id = [...client.conversations.keys()][0];
    await act(async () => {
      client.conversations.set(id, { ...client.conversations.get(id)!, state: "answered", reply: "I can build tools for you.", delivery: "answer" });
    });
    await waitFor(() => expect(spoken).toEqual(["I can build tools for you."]), { timeout: 4000 });
  });
});
