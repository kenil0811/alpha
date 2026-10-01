import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Creation } from "../core/client";
import { FakeWorkflowsClient, sampleDetail, sampleSummary } from "../test/fakeWorkflows";
import { ModulePage } from "../modules/ModulePage";
import { ActionsView } from "./ActionsView";
import { CreationCard } from "./CreationCard";
import { formFields, humanize, toInput } from "./schemaForm";

function ready(creation: Creation, overrides: Partial<NonNullable<Creation["result"]>> = {}): Creation {
  return {
    ...creation,
    state: "active",
    stage: "active",
    label: "Ready to use",
    app_id: "notes-list-1a2b3c",
    app_name: "Notes list",
    result: {
      app_id: "notes-list-1a2b3c",
      name: "Notes list",
      actions: ["add_note"],
      has_ui: true,
      checks_passed: 28,
      preview_images: [{ name: "populated-1280", url: "/api/builds/b1/evidence/1/populated-1280.png" }],
      attempts: 1,
      ...overrides,
    },
  };
}

describe("creating a result", () => {
  it("starts, shows progress in plain stages and opens the ready result", async () => {
    const client = new FakeWorkflowsClient();
    const opened: string[] = [];
    const user = userEvent.setup();
    render(<CreationCard client={client} conversationId="conv_1" briefRevision={1} unavailable={["email"]} onOpen={(id) => opened.push(id)} />);

    await user.click(await screen.findByRole("button", { name: "Create it" }));
    const progress = await screen.findByLabelText("Creating it");
    expect(within(progress).getByText(/Deciding how to check it/, { selector: "li" })).toHaveTextContent("(in progress)");

    client.nextCreationState = (c) => ready(c);
    const card = await screen.findByLabelText("Notes list is ready", {}, { timeout: 3000 });
    expect(card).toHaveTextContent("It passed all 28 of its checks.");
    expect(card).toHaveTextContent("Not connected yet, so not part of it: email.");
    const preview = await within(card).findByRole("figure");
    expect(preview).toHaveTextContent("Preview");
    expect(within(preview).getByRole("img", { name: "Preview: With several entries" })).toBeInTheDocument();
    expect(client.imagesRequested).toEqual(["/api/builds/b1/evidence/1/populated-1280.png"]);

    await user.click(screen.getByRole("button", { name: "Open Notes list" }));
    expect(opened).toEqual(["notes-list-1a2b3c"]);
  });

  it("tells the person a fast-lane module is on while its checks run, then offers the way back", async () => {
    const client = new FakeWorkflowsClient();
    const user = userEvent.setup();
    render(<CreationCard client={client} conversationId="conv_1" briefRevision={1} unavailable={[]} onOpen={() => undefined} />);
    await user.click(await screen.findByRole("button", { name: "Create it" }));
    client.nextCreationState = (c) => ready(c, { checks: { status: "pending" } });
    const card = await screen.findByLabelText("Notes list is ready", {}, { timeout: 3000 });
    expect(card).toHaveTextContent("Its structure checked out.");
    expect(card).toHaveTextContent("Alpha is still checking how it behaves");
    expect(card).not.toHaveTextContent("passed all");

    // The checks land later, while the card is still followed.
    const current = client.creations.get([...client.creations.keys()][0])!;
    client.creations.set(current.creation_id, { ...current, result: { ...current.result!, checks: { status: "failed", failed_checks: ["the count was wrong"] } } });
    await screen.findByText(/Alpha's later checks found a problem: the count was wrong/, {}, { timeout: 5000 });
    await user.click(screen.getByRole("button", { name: "Remove it" }));
    expect(client.removed).toEqual(["notes-list-1a2b3c"]);
    expect(await screen.findByText(/Taken out of use/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open Notes list" })).not.toBeInTheDocument();
  });

  it("says plainly when a module was checked only on the request's examples", async () => {
    const client = new FakeWorkflowsClient();
    const user = userEvent.setup();
    render(<CreationCard client={client} conversationId="conv_1" briefRevision={1} unavailable={[]} onOpen={() => undefined} />);
    await user.click(await screen.findByRole("button", { name: "Create it" }));
    client.nextCreationState = (c) => ready(c, { checks: { status: "preliminary", full: "pending", checks_passed: 2 } });
    const card = await screen.findByLabelText("Notes list is ready", {}, { timeout: 3000 });
    expect(card).toHaveTextContent("It was checked only against the examples in your request (2 checks)");
    expect(card).toHaveTextContent("full checks are being written again");
    expect(card).not.toHaveTextContent("passed all");

    // The retry could not write them either: said once, and it stays on.
    const current = client.creations.get([...client.creations.keys()][0])!;
    client.creations.set(current.creation_id, { ...current, result: { ...current.result!, checks: { status: "preliminary", full: "unavailable", checks_passed: 2 } } });
    await screen.findByText(/Alpha couldn't write its full checks/, {}, { timeout: 5000 });
    expect(screen.getByRole("button", { name: "Open Notes list" })).toBeInTheDocument();
  });

  it("says what went wrong and what to do next when it could not be made", async () => {
    const client = new FakeWorkflowsClient();
    const user = userEvent.setup();
    render(<CreationCard client={client} conversationId="conv_1" briefRevision={1} unavailable={[]} onOpen={() => undefined} />);
    await user.click(await screen.findByRole("button", { name: "Create it" }));
    client.nextCreationState = (c) => ({
      ...c,
      state: "failed",
      failure: {
        reason: "checks_failed",
        message: "It was built but did not pass its checks after 3 tries.",
        next_step: "revise",
        failed_checks: ["scenario.example_1: the total did not include the second entry"],
      },
    });
    expect(await screen.findByRole("alert", {}, { timeout: 3000 })).toHaveTextContent("did not pass its checks after 3 tries");
    expect(screen.getByText(/Add or remove a detail below/)).toBeInTheDocument();
    // The checks' own vocabulary stays in the record, never on the card a person reads.
    expect(screen.queryByText(/the total did not include the second entry/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Open/ })).not.toBeInTheDocument();
  });

  it("stops a creation and offers to start again without switching anything on", async () => {
    const client = new FakeWorkflowsClient();
    const user = userEvent.setup();
    render(<CreationCard client={client} conversationId="conv_1" briefRevision={1} unavailable={[]} onOpen={() => undefined} />);
    await user.click(await screen.findByRole("button", { name: "Create it" }));
    await user.click(await screen.findByRole("button", { name: "Stop" }));
    expect(await screen.findByText("Stopped. Nothing was switched on.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create it again" })).toBeInTheDocument();
  });

  it("picks up the creation already running for this brief revision", async () => {
    const client = new FakeWorkflowsClient();
    const existing = await client.startCreation("conv_1");
    client.creations.set(existing.creation_id, ready(existing));
    render(<CreationCard client={client} conversationId="conv_1" briefRevision={1} unavailable={[]} onOpen={() => undefined} />);
    expect(await screen.findByLabelText("Notes list is ready")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create it" })).not.toBeInTheDocument();
  });
});

describe("home and the rail", () => {
  it("lists modules in the rail and on Home, and opens one", async () => {
    const { App } = await import("../App");
    const client = new FakeWorkflowsClient();
    client.apps = [sampleSummary(), sampleSummary({ app_id: "tracker-9f", name: "Tracker", has_ui: true, actions: 3 })];
    client.details.set("tracker-9f", sampleDetail({ app_id: "tracker-9f", name: "Tracker" }));
    const user = userEvent.setup();
    render(<App client={client} />);
    expect(await screen.findByText("Runtime connected")).toBeInTheDocument();
    const rail = screen.getByRole("navigation", { name: "Alpha" });
    expect(await within(rail).findByRole("button", { name: "Tracker" })).toBeInTheDocument();
    expect(screen.getByText("Has its own screen")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open Tracker" }));
    expect(await screen.findByRole("heading", { name: "Tracker" })).toBeInTheDocument();
    expect(within(rail).getByRole("button", { name: "Tracker" })).toHaveAttribute("aria-current", "page");
    await user.click(within(rail).getByRole("button", { name: "Home" }));
    expect(await screen.findByRole("heading", { name: "Your projects" })).toBeInTheDocument();
    await act(async () => undefined);
  });
});

describe("an App without its own screen", () => {
  it("runs an action from a form built from its inputs and shows the saved result", async () => {
    const client = new FakeWorkflowsClient();
    client.details.set("notes-list-1a2b3c", sampleDetail());
    client.actionOutput = { id: "rec_1", revision: 1, saved_title: "Buy milk" };
    const user = userEvent.setup();
    render(<ModulePage client={client} appId="notes-list-1a2b3c" onAsk={() => undefined} />);

    expect(await screen.findByRole("heading", { name: "Notes list" })).toBeInTheDocument();
    await user.click(await screen.findByRole("tab", { name: "Actions" }));
    expect(await screen.findByText("What to remember")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Title"), "Buy milk");
    await user.click(screen.getByLabelText("Pinned (optional)"));
    client.records.set("notes-list-1a2b3c/notes", [
      {
        id: "rec_1",
        revision: 1,
        values: { title: "Buy milk", calories: 120 },
        provenance: { calories: { source: "model_estimate" } },
        created_at: "2026-09-26T10:00:00Z",
        updated_at: "2026-09-26T10:00:00Z",
      },
    ]);
    await user.click(screen.getByRole("button", { name: "Run" }));

    const status = await screen.findByText("Done.");
    expect(status.parentElement).toHaveTextContent("Saved titleBuy milk");
    expect(client.invocations).toEqual([
      { appId: "notes-list-1a2b3c", actionId: "add_note", input: { title: "Buy milk", pinned: true }, origin: "user" },
    ]);
    // The saved record is on the module's own Notes page, labelled as an estimate where it is one.
    await user.click(screen.getByRole("tab", { name: "Notes" }));
    const table = await screen.findByRole("table");
    expect(await within(table).findByText("Buy milk")).toBeInTheDocument();
    expect(within(table).getByLabelText("estimate")).toBeInTheDocument();
  });

  it("refuses a missing required input before running and shows a failed run's reason", async () => {
    const client = new FakeWorkflowsClient();
    client.actionOutcome = () => "failed";
    const user = userEvent.setup();
    render(<ActionsView client={client} appId="notes" actions={sampleDetail().actions} onChanged={() => undefined} />);
    await user.click(screen.getByRole("button", { name: "Run" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Not done. Title is needed.");
    expect(client.invocations).toHaveLength(0);

    await user.type(screen.getByLabelText("Title"), "x");
    await user.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Not done. The food is needed."));
  });

  it("stops a long-running action", async () => {
    const client = new FakeWorkflowsClient();
    client.actionOutcome = () => "running";
    const user = userEvent.setup();
    render(<ActionsView client={client} appId="notes" actions={sampleDetail().actions} onChanged={() => undefined} />);
    await user.type(screen.getByLabelText("Title"), "slow");
    await user.click(screen.getByRole("button", { name: "Run" }));
    await user.click(await screen.findByRole("button", { name: "Stop" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("You stopped it."), { timeout: 3000 });
    expect(client.cancelled).toEqual(["run_1"]);
  });

  it("uses the UI origin for actions a person cannot run directly", async () => {
    const client = new FakeWorkflowsClient();
    const [action] = sampleDetail().actions;
    const user = userEvent.setup();
    render(<ActionsView client={client} appId="notes" actions={[{ ...action, invocable_from: ["ui"] }]} onChanged={() => undefined} />);
    await user.type(screen.getByLabelText("Title"), "a");
    await user.click(screen.getByRole("button", { name: "Run" }));
    await screen.findByText("Done.");
    expect(client.invocations[0].origin).toBe("ui");
  });
});

describe("an App with its own compiled screen", () => {
  it("explains outside the native window that only the actions are available", async () => {
    const client = new FakeWorkflowsClient();
    client.details.set("notes-list-1a2b3c", sampleDetail({ ui: { entry: "ui/src/main.tsx", views: [], actions: ["add_note"] } }));
    render(<ModulePage client={client} appId="notes-list-1a2b3c" onAsk={() => undefined} />);
    expect(await screen.findByText(/This App's screen opens in the Alpha window on your Mac/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Actions" })).toBeInTheDocument();
    expect(screen.getByText(/Its records stay on this Mac\./)).toBeInTheDocument();
    expect(screen.queryByText(/pyprof/)).not.toBeInTheDocument();
  });
});

describe("form fields from an input schema", () => {
  const schema = {
    type: "object",
    properties: {
      food: { type: "string" },
      notes: { type: "string" },
      grams: { type: "number", title: "Amount (g)" },
      servings: { type: "integer" },
      meal: { type: "string", enum: ["breakfast", "lunch"] },
      done: { type: "boolean" },
      tags: { type: ["array", "null"], items: { type: "string" } },
    },
    required: ["food", "grams"],
  };

  it("chooses a control per type with plain labels", () => {
    const fields = formFields(schema);
    expect(fields.map((f) => [f.name, f.kind, f.label, f.required])).toEqual([
      ["food", "text", "Food", true],
      ["notes", "longtext", "Notes", false],
      ["grams", "number", "Amount (g)", true],
      ["servings", "integer", "Servings", false],
      ["meal", "choice", "Meal", false],
      ["done", "boolean", "Done", false],
      ["tags", "lines", "Tags", false],
    ]);
    expect(humanize("food_entries")).toBe("Food entries");
  });

  it("converts values and reports problems in plain words", () => {
    const fields = formFields(schema);
    expect(toInput(fields, { food: " apple ", grams: "150", servings: "2", tags: "fruit\n\n  sweet  ", done: true })).toEqual({
      input: { food: "apple", grams: 150, servings: 2, tags: ["fruit", "sweet"], done: true },
      problems: [],
    });
    expect(toInput(fields, { grams: "lots", servings: "1.5" }).problems).toEqual([
      "Food is needed.",
      "Amount (g) must be a number.",
      "Servings must be a whole number.",
    ]);
  });
});

describe("what the shell says around an App's own screen", () => {
  it("speaks only about blocked requests and an App that cannot run", async () => {
    const { screenProblem } = await import("./GeneratedScreen");
    expect(screenProblem({ code: "forbidden" })).toMatch(/blocked a request/);
    expect(screenProblem({ code: "unsupported" })).toMatch(/can't run right now/);
    expect(screenProblem({ code: "invalid_request", message: "Food is needed" })).toBeNull();
    expect(screenProblem({ internal: "TypeError" })).toBeNull();
  });
});

describe("where the data goes", () => {
  it("shows Core's statement for an App that sends things for estimates", async () => {
    const client = new FakeWorkflowsClient();
    const notice = "Its records stay on this Mac. To make an estimate, it sends what the estimate is about (such as a description you typed) to Anthropic's Claude service over the internet.";
    client.details.set("notes-list-1a2b3c", sampleDetail({ data_notice: notice }));
    render(<ModulePage client={client} appId="notes-list-1a2b3c" onAsk={() => undefined} />);
    await screen.findByRole("heading", { name: "Notes list" });
    expect(await screen.findByText(new RegExp(notice.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))).toBeInTheDocument();
  });
});

describe("stopping at the end of a creation", () => {
  it("offers no Stop once switching on has begun", async () => {
    const client = new FakeWorkflowsClient();
    const started = await client.startCreation("conv_1");
    client.creations.set(started.creation_id, { ...started, state: "activating", stage: "activating", label: "Getting it ready to use" });
    render(<CreationCard client={client} conversationId="conv_1" briefRevision={1} unavailable={[]} onOpen={() => undefined} />);
    expect(await screen.findByText(/this can no longer be stopped/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
  });

  it("shows Core's answer when Stop arrives too late", async () => {
    const client = new FakeWorkflowsClient();
    client.cancelCreation = async () => {
      throw new Error("it is already being switched on and can no longer be stopped");
    };
    const user = userEvent.setup();
    render(<CreationCard client={client} conversationId="conv_1" briefRevision={1} unavailable={[]} onOpen={() => undefined} />);
    await user.click(await screen.findByRole("button", { name: "Create it" }));
    await user.click(await screen.findByRole("button", { name: "Stop" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("can no longer be stopped");
  });
});
