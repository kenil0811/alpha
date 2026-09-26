/**
 * M1 review findings F02 and F06 (repair task M1-R01): a request and its creation stay reachable
 * across navigation and reopening, a temporary status failure recovers by itself, and a failed
 * assistant turn always offers a next step with the request kept.
 */
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import type { Conversation, Creation } from "../core/client";
import { sampleBrief } from "../test/fakeClient";
import { FakeWorkflowsClient } from "../test/fakeWorkflows";

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
  expect(await screen.findByRole("status")).toHaveTextContent("Runtime connected");
  await user.type(screen.getByLabelText("What do you want done?"), text);
  await user.click(screen.getByRole("button", { name: "Ask Alpha" }));
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

    await user.click(screen.getByRole("button", { name: "My workflows" }));
    const making = await screen.findByRole("region", { name: "Being made" });
    expect(within(making).getByText("Deciding how to check it")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Activity" }));
    await user.click(screen.getByRole("button", { name: "Assistant" }));

    expect(await screen.findByText("Keep a notes list for me")).toBeInTheDocument();
    const progress = await screen.findByLabelText("Creating it");
    expect(within(progress).getByRole("button", { name: "Stop" })).toBeInTheDocument();
    expect([...client.creations.keys()]).toEqual([creationId]);

    // From My workflows, "View progress" leads back to the same request.
    await user.click(screen.getByRole("button", { name: "My workflows" }));
    await user.click(await screen.findByRole("button", { name: "View progress" }));
    expect(await screen.findByLabelText("Creating it")).toBeInTheDocument();
    expect(screen.getByText("Keep a notes list for me")).toBeInTheDocument();
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
    await user.click(screen.getByRole("button", { name: "New request" }));

    const recent = await screen.findByRole("navigation", { name: "Recent requests" });
    const item = within(recent).getByRole("button", { name: /Keep a notes list for me/ });
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
    expect(await screen.findByRole("status")).toHaveTextContent("Runtime connected");
    await user.type(screen.getByLabelText("What do you want done?"), "Plan my week");
    await user.click(screen.getByRole("button", { name: "Ask Alpha" }));

    const failure = await screen.findByRole("alert", { name: "Alpha could not work this out" });
    expect(failure).toHaveTextContent("the model service took too long to answer");
    client.retryScript = (c) => ({ ...c, state: "answered", delivery: "answer", reply: "Here is a plan for your week." });
    await user.click(within(failure).getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Here is a plan for your week.")).toBeInTheDocument();
    expect(client.retries).toBe(1);

    await user.click(screen.getByRole("button", { name: "Start over" }));
    expect(screen.getByLabelText("What do you want done?")).toHaveValue("Plan my week");
    await act(async () => undefined);
  });

  it("offers Start over while a failed turn cannot be retried yet", async () => {
    const client = new FakeWorkflowsClient();
    client.assistantScript = (c) => ({ ...c, state: "failed", error: "Alpha was closed or restarted while it was thinking about this" });
    const user = userEvent.setup();
    render(<App client={client} />);
    expect(await screen.findByRole("status")).toHaveTextContent("Runtime connected");
    await user.type(screen.getByLabelText("What do you want done?"), "Sort my receipts");
    await user.click(screen.getByRole("button", { name: "Ask Alpha" }));
    const failure = await screen.findByRole("alert", { name: "Alpha could not work this out" });
    await user.click(within(failure).getByRole("button", { name: "Start over" }));
    await waitFor(() => expect(screen.getByLabelText("What do you want done?")).toHaveValue("Sort my receipts"));
  });
});

describe("changing a request after its App was made (review finding F07)", () => {
  it("offers a separate workflow instead of silently making a second App", async () => {
    const client = briefedClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    await askAndCreate(user);
    expect(screen.queryByLabelText("Change or add something")).not.toBeInTheDocument();
    expect(screen.getByText(/You can change the request once this attempt finishes/)).toBeInTheDocument();

    client.nextCreationState = ready;
    await screen.findByLabelText("Notes list is ready", {}, { timeout: 3000 });
    const after = await screen.findByLabelText("After it was made");
    expect(after).toHaveTextContent("Changing Notes list after it was made isn't possible yet");
    expect(screen.queryByLabelText("Change or add something")).not.toBeInTheDocument();

    await user.click(within(after).getByRole("button", { name: "Create a separate workflow" }));
    expect(screen.getByLabelText("What do you want done?")).toHaveValue("Keep a notes list for me");
    expect(client.creations.size).toBe(1);
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
    expect(await screen.findByLabelText("After it was made")).toHaveTextContent("Changing Notes (made) after it was made");
  });

  it("still lets the person correct the request before anything is made", async () => {
    const client = briefedClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    expect(await screen.findByRole("status")).toHaveTextContent("Runtime connected");
    await user.type(screen.getByLabelText("What do you want done?"), "Keep a notes list for me");
    await user.click(screen.getByRole("button", { name: "Ask Alpha" }));
    await screen.findByRole("button", { name: "Create it" });
    expect(screen.getByLabelText("Change or add something")).toBeInTheDocument();
  });
});
