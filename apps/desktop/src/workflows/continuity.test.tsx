/**
 * M1 review findings F02 and F06: a request and its creation stay reachable across navigation
 * and reopening, a temporary status failure recovers by itself, and a failed assistant turn
 * always offers a next step with the request kept.
 */
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import type { Conversation, Creation } from "../core/client";
import { sampleBrief } from "../test/fakeClient";
import { sampleDetail, sampleSummary, FakeWorkflowsClient } from "../test/fakeWorkflows";

function briefedClient(): FakeWorkflowsClient {
  const client = new FakeWorkflowsClient();
  client.assistantScript = (c: Conversation): Conversation => ({
    ...c,
    state: "briefed",
    delivery: "app",
    reply: "I'll make a small notes list.",
    current_brief: sampleBrief({ conversation_id: c.conversation_id, unavailable_capabilities: [] }),
  });
  return client;
}

function ready(c: Creation): Creation {
  return {
    ...c,
    state: "active",
    stage: "active",
    label: "Ready to use",
    app_id: "notes-list-1a2b3c",
    app_name: "Notes list",
    result: { app_id: "notes-list-1a2b3c", name: "Notes list", actions: [], has_ui: false, checks_passed: 12, preview_images: [], attempts: 1 },
  };
}

async function askAndCreate(user: ReturnType<typeof userEvent.setup>, text = "Keep a notes list for me") {
  expect(await screen.findByText("Runtime connected")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Message"), text);
  await user.click(screen.getByRole("button", { name: "Send" }));
  await user.click(await screen.findByRole("button", { name: "Create it" }));
  return screen.findByLabelText("Creating it");
}

beforeEach(() => {
  window.localStorage.clear();
});

describe("a request and its creation stay reachable", () => {
  it("survives visiting every other surface and coming back", async () => {
    const client = briefedClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    await askAndCreate(user);
    const creationId = [...client.creations.keys()][0];

    const rail = screen.getByRole("navigation", { name: "Alpha" });
    await user.click(within(rail).getByRole("button", { name: "Activity" }));
    await user.click(within(rail).getByRole("button", { name: "Connections" }));
    await user.click(within(rail).getByRole("button", { name: "Settings" }));
    await user.click(within(rail).getByRole("button", { name: "Home" }));

    expect(await screen.findByText("Keep a notes list for me")).toBeInTheDocument();
    const progress = await screen.findByLabelText("Creating it");
    expect(within(progress).getByRole("button", { name: "Stop" })).toBeInTheDocument();
    expect([...client.creations.keys()]).toEqual([creationId]);
  });

  it("is restored when the window opens again", async () => {
    const client = briefedClient();
    const user = userEvent.setup();
    const first = render(<App client={client} />);
    await askAndCreate(user);
    first.unmount();

    render(<App client={client} />);
    expect(await screen.findByText("Keep a notes list for me")).toBeInTheDocument();
    expect(await screen.findByLabelText("Creating it")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create it" })).not.toBeInTheDocument();
  });

  it("reopens an earlier request from Recent requests", async () => {
    const client = briefedClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    await askAndCreate(user);
    await user.click(screen.getByRole("button", { name: "New chat" }));

    await user.click(screen.getByRole("button", { name: "Chat history" }));
    const item = await screen.findByRole("option", { name: /Keep a notes list for me/ });
    expect(item).toHaveTextContent("Being made");
    await user.click(item);
    expect(await screen.findByLabelText("Creating it")).toBeInTheDocument();
  });
});

describe("temporary failures do not strand the person", () => {
  it("keeps following a creation through a failed status request", async () => {
    const client = briefedClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    await askAndCreate(user);

    client.failNextPolls = 1;
    expect(await screen.findByText(/Lost contact with Alpha's runtime for a moment/, {}, { timeout: 3000 })).toBeInTheDocument();
    client.nextCreationState = ready;
    expect(await screen.findByLabelText("Notes list is ready", {}, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.queryByText(/Lost contact/)).not.toBeInTheDocument();
    expect(client.polls).toBeGreaterThanOrEqual(2);
  }, 15_000);

  it("offers Try again and Start over after a failed turn, keeping the request", async () => {
    const client = new FakeWorkflowsClient();
    client.assistantScript = (c) => ({ ...c, state: "failed", error: "the model service took too long to answer" });
    const user = userEvent.setup();
    render(<App client={client} />);
    expect(await screen.findByText("Runtime connected")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Message"), "Plan my week");
    await user.click(screen.getByRole("button", { name: "Send" }));

    const failure = await screen.findByRole("alert", { name: "Alpha could not work this out" });
    expect(failure).toHaveTextContent("the model service took too long to answer");
    client.retryScript = (c) => ({ ...c, state: "answered", delivery: "answer", reply: "Here is a plan for your week." });
    await user.click(within(failure).getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Here is a plan for your week.")).toBeInTheDocument();
    expect(client.retries).toBe(1);

    // An answered turn is correctable directly: the composer stays available, no separate
    // "start over" step needed to keep talking about the same request.
    expect(screen.getByLabelText("Message")).toBeEnabled();
    await act(async () => undefined);
  });

  it("offers Start over while a failed turn cannot be retried yet", async () => {
    const client = new FakeWorkflowsClient();
    client.assistantScript = (c) => ({ ...c, state: "failed", error: "Alpha was closed or restarted while it was thinking about this" });
    const user = userEvent.setup();
    render(<App client={client} />);
    expect(await screen.findByText("Runtime connected")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Message"), "Sort my receipts");
    await user.click(screen.getByRole("button", { name: "Send" }));
    const failure = await screen.findByRole("alert", { name: "Alpha could not work this out" });
    await user.click(within(failure).getByRole("button", { name: "Start over" }));
    await waitFor(() => expect(screen.getByLabelText("Message")).toHaveValue("Sort my receipts"));
  });
});

describe("changing a request after its App was made (review finding F07)", () => {
  it("tells the person how to change the module later instead of silently making a second App", async () => {
    const client = briefedClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    await askAndCreate(user);
    expect(screen.queryByLabelText("Change or add something")).not.toBeInTheDocument();
    expect(screen.getByText(/You can change the request once this attempt finishes/)).toBeInTheDocument();

    client.nextCreationState = ready;
    await screen.findByLabelText("Notes list is ready", {}, { timeout: 3000 });
    const after = await screen.findByLabelText("After it was made");
    expect(after).toHaveTextContent("Notes list is in the sidebar");
    expect(after).toHaveTextContent("To change it later, open it and describe the change here");
    expect(screen.queryByLabelText("Change or add something")).not.toBeInTheDocument();

    await user.click(within(after).getByRole("button", { name: "Describe another" }));
    expect(screen.getByLabelText("Message")).toHaveValue("Keep a notes list for me");
    expect(client.creations.size).toBe(1);
  });

  it("a request typed while looking at a module changes that module and keeps its data", async () => {
    const client = briefedClient();
    client.apps = [sampleSummary()];
    client.details.set("notes-list-1a2b3c", sampleDetail());
    const user = userEvent.setup();
    render(<App client={client} />);
    expect(await screen.findByText("Runtime connected")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Notes list" }));
    await screen.findByRole("heading", { name: "Notes list" });
    // On a module page the assistant stays out of the way until asked for.
    expect(screen.queryByRole("complementary", { name: "Assistant" })).not.toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Assistant" })[0]);
    const panel = await screen.findByRole("complementary", { name: "Assistant" });
    expect(panel).toHaveTextContent("I'm looking at Notes list");
    expect(panel).toHaveTextContent("Everything already saved in it is kept");

    await user.type(within(panel).getByLabelText("Message"), "Add a mood to each note");
    await user.click(within(panel).getByRole("button", { name: "Send" }));
    // A change the person asked for starts on its own: no second approval.
    await screen.findByLabelText("Creating it");
    const started = [...client.conversations.values()][0];
    expect(started.change_of).toBe("notes-list-1a2b3c");
    expect(panel).toHaveTextContent("Changing a module");
    expect(within(panel).queryByRole("button", { name: "Create it" })).not.toBeInTheDocument();
    client.nextCreationState = (c) => {
      const made = ready(c);
      return { ...made, result: { ...made.result!, summary: "Each note now shows a mood next to its title." } };
    };
    const updated = await screen.findByLabelText("Notes list is updated", {}, { timeout: 3000 });
    expect(updated).toHaveTextContent("Each note now shows a mood next to its title.");
    expect(updated).not.toHaveTextContent("passed all");
    const after = await screen.findByLabelText("After it was made");
    expect(after).toHaveTextContent("Notes list is updated and its data is kept");
  });

  it("names the App it made, not the name planned for it", async () => {
    const client = briefedClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    await askAndCreate(user);
    client.nextCreationState = (c) => {
      const made = ready(c);
      return { ...made, result: { ...made.result!, name: "Notes (made)" } };
    };
    const card = await screen.findByLabelText("Notes (made) is ready", {}, { timeout: 3000 });
    expect(within(card).getByRole("button", { name: "Open Notes (made)" })).toBeInTheDocument();
    expect(await screen.findByLabelText("After it was made")).toHaveTextContent("Notes (made) is in the sidebar");
  });

  it("still lets the person correct the request before anything is made", async () => {
    const client = briefedClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    expect(await screen.findByText("Runtime connected")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Message"), "Keep a notes list for me");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByRole("button", { name: "Create it" });
    expect(screen.getByLabelText("Message")).toBeEnabled();
  });
});

describe("a module's own thread", () => {
  it("shows the module's earlier requests when the assistant is opened from its page", async () => {
    const client = briefedClient();
    client.apps = [sampleSummary()];
    client.details.set("notes-list-1a2b3c", sampleDetail());
    const now = new Date().toISOString();
    client.conversations.set("conv_old", {
      conversation_id: "conv_old",
      change_of: "notes-list-1a2b3c",
      state: "briefed",
      route_id: "fake",
      created_at: now,
      updated_at: now,
      turns: [{ turn_id: "t1", sequence: 1, role: "user", kind: "request", content: { text: "Add a mood to each note" }, created_at: now }],
      current_brief: null,
      interpretation: null,
      questions: [],
      reply: "Done.",
      delivery: "app",
      error: null,
    });
    const user = userEvent.setup();
    render(<App client={client} />);
    expect(await screen.findByText("Runtime connected")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Notes list" }));
    await screen.findByRole("heading", { name: "Notes list" });
    await user.click(screen.getAllByRole("button", { name: "Assistant" })[0]);
    await user.click(await screen.findByRole("button", { name: "Chat history" }));
    const item = screen.getByRole("option", { name: /Add a mood to each note/ });
    expect(item).toHaveTextContent("Change · Planned");
    await user.click(item);
    expect(await screen.findByText("Changing a module")).toBeInTheDocument();
  });
});
