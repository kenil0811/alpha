/**
 * The declarative screen: the shell draws a module's tabs and blocks from its declaration,
 * reading through declared views and writing through declared actions.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { AppDetail } from "../core/client";
import { FakeWorkflowsClient, sampleDetail } from "../test/fakeWorkflows";
import { ModulePage } from "./ModulePage";

function screenDetail(): AppDetail {
  return sampleDetail({
    app_id: "log-1",
    name: "Daily log",
    collections: [
      {
        name: "entries",
        fields: [
          { name: "when", kind: "date", required: true },
          { name: "title", kind: "text", required: true },
          { name: "amount", kind: "number" },
          { name: "category", kind: "choice", choices: ["morning", "evening"] },
        ],
      },
    ],
    actions: [
      {
        id: "quick_add",
        title: "Log something",
        description: "One line",
        input_schema: { type: "object", properties: { text: { type: "string" } }, required: ["text"] },
        output_schema: { type: "object" },
        invocable_from: ["ui", "manual"],
        effect_class: "local_write",
      },
      {
        id: "correct_entry",
        title: "Fix an entry",
        description: "Change or remove",
        input_schema: { type: "object", properties: { entry: { type: "string" }, amount: { type: "number" }, delete: { type: "boolean" } }, required: ["entry"] },
        output_schema: { type: "object" },
        invocable_from: ["ui"],
        effect_class: "local_write",
      },
    ],
    views: [
      { id: "entries.all", kind: "records", collection: "entries", where: null, fields: null, filterable: ["title", "category"], sortable: ["when", "amount"], default_order: [], max_limit: 100, group_by: [], metrics: [] },
      { id: "entries.by_day", kind: "aggregate", collection: "entries", where: null, fields: null, filterable: [], sortable: [], default_order: [], max_limit: 100, group_by: [{ field: "when", bucket: "day" }], metrics: [{ name: "total", fn: "sum", field: "amount" }] },
    ],
    has_screen: true,
    screen: {
      icon: "▤",
      tabs: [
        {
          id: "log",
          title: "Log",
          blocks: [
            { kind: "quick_entry", action: "quick_add", input: "text", placeholder: "What happened?", voice: false, extra: {} },
            {
              kind: "table",
              view: "entries.all",
              columns: [
                { field: "when", format: "date", editable: false },
                { field: "title", editable: true },
                { field: "amount", format: "number", unit: "units", editable: true },
                { field: "category", format: "pill", editable: false },
              ],
              lists: [{ id: "morning", title: "Mornings", where: { field: "category", op: "eq", value: "morning" } }],
              edit: { action: "correct_entry", id_param: "entry", input: {} },
              delete: { action: "correct_entry", id_param: "entry", input: { delete: true } },
              detail: { title_field: "title", fields: [], long_fields: ["note"], actions: [{ action: "correct_entry", id_param: "entry", input: { starred: true }, title: "Star" }] },
              row_actions: [],
              totals: ["amount"],
              page_size: 50,
            },
            { kind: "metrics", cards: [{ title: "Today", view: "entries.by_day", metric: "total", unit: "units", goal: 500 }] },
            { kind: "form", action: "correct_entry", title: "Fix an entry by hand", description: null, submit_label: "Save", prefill_view: null },
          ],
        },
        { id: "notes", title: "Notes", blocks: [{ kind: "text", body: "Plain words." }] },
      ],
    },
  });
}

const today = (() => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
})();

function clientWithRows(): FakeWorkflowsClient {
  const client = new FakeWorkflowsClient();
  client.details.set("log-1", screenDetail());
  client.views.set("entries.all", {
    records: [
      { id: "r1", revision: 1, values: { when: today, title: "long walk", amount: 120, category: "morning", note: "Along the river.\nSaw a heron." }, created_at: "2026-09-27T08:00:00Z", updated_at: "2026-09-27T08:00:00Z" },
      { id: "r2", revision: 1, values: { when: today, title: "swim", amount: 30, category: "evening" }, provenance: { amount: { source: "model_estimate" } }, created_at: "", updated_at: "" },
    ],
    next_cursor: null,
  });
  client.views.set("entries.by_day", { groups: [{ key: { when_day: today }, values: { total: 150 } }], truncated: false });
  return client;
}

describe("a module with a declared screen", () => {
  it("draws the tabs, the table with totals and the metric from its views", async () => {
    const client = clientWithRows();
    render(<ModulePage client={client} appId="log-1" onAsk={() => undefined} />);
    expect(await screen.findByRole("heading", { name: "Daily log" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Log" })).toHaveAttribute("aria-selected", "true");
    const table = await screen.findByRole("table");
    expect(within(table).getByText("long walk")).toBeInTheDocument();
    expect(within(table).getByText("120 units")).toBeInTheDocument();
    expect(within(table).getByLabelText("estimate")).toHaveAttribute("title", expect.stringContaining("estimate"));
    expect(within(table).getByText("150 units")).toBeInTheDocument(); // total
    expect(screen.getByText("Today")).toBeInTheDocument();
    expect(await screen.findByText("350 units left")).toBeInTheDocument();
    expect(screen.queryByText(/pyprof|ver_/)).not.toBeInTheDocument();
  });

  it("logs a line through the quick entry and shows the action's message", async () => {
    const client = clientWithRows();
    client.actionOutput = { id: "r3", revision: 1, message: "Logged “tea”." };
    const user = userEvent.setup();
    render(<ModulePage client={client} appId="log-1" onAsk={() => undefined} />);
    const box = await screen.findByLabelText("What happened?");
    await user.type(box, "tea{Enter}");
    expect(await screen.findByText("Logged “tea”.")).toBeInTheDocument();
    expect(client.invocations[0]).toMatchObject({ actionId: "quick_add", input: { text: "tea" }, origin: "user" });
    await waitFor(() => expect(box).toHaveValue(""));
  });

  it("edits a cell through the edit action and filters through a saved list", async () => {
    const client = clientWithRows();
    const user = userEvent.setup();
    render(<ModulePage client={client} appId="log-1" onAsk={() => undefined} />);
    const table = await screen.findByRole("table");
    await user.click(await within(table).findByText("30 units"));
    const input = await within(table).findByRole("spinbutton", { name: "Amount" });
    await user.clear(input);
    await user.type(input, "45{Enter}");
    await waitFor(() => expect(client.invocations[0]).toMatchObject({ actionId: "correct_entry", input: { entry: "r2", amount: 45 } }));

    const tableQueries = () => client.viewQueries.filter((q) => q.viewId === "entries.all");
    expect(tableQueries().at(-1)?.body).toMatchObject({ where: { field: "category", op: "eq", value: "morning" } });
    await user.selectOptions(screen.getByLabelText("Which entries"), "all");
    await waitFor(() => expect(tableQueries().at(-1)?.body.where).toBeUndefined());
  });

  it("switches tabs", async () => {
    const client = clientWithRows();
    const user = userEvent.setup();
    render(<ModulePage client={client} appId="log-1" onAsk={() => undefined} />);
    await user.click(await screen.findByRole("tab", { name: "Notes" }));
    expect(screen.getByText("Plain words.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("a table's detail page", () => {
  it("opens from a row with every field, long text, when it was added and its actions", async () => {
    const client = clientWithRows();
    const user = userEvent.setup();
    render(<ModulePage client={client} appId="log-1" onAsk={() => undefined} />);
    const table = await screen.findByRole("table");
    await user.click(await within(table).findByRole("row", { name: "Open long walk" }));
    const drawer = await screen.findByRole("region", { name: "long walk" });
    expect(within(drawer).getByText(/Along the river/)).toBeInTheDocument();
    expect(within(drawer).getByText("Added")).toBeInTheDocument();
    expect(within(drawer).getByText("Amount")).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "Star" }));
    await waitFor(() => expect(client.invocations.at(-1)).toMatchObject({ actionId: "correct_entry", input: { entry: "r1", starred: true } }));
    await user.click(within(drawer).getByRole("button", { name: "Close details" }));
    expect(screen.queryByRole("region", { name: "long walk" })).not.toBeInTheDocument();
  });
});

describe("quick filters on a table", () => {
  it("offers a dropdown for each choice column the view can filter on and narrows the query", async () => {
    const client = clientWithRows();
    const user = userEvent.setup();
    render(<ModulePage client={client} appId="log-1" onAsk={() => undefined} />);
    await screen.findByRole("table");
    const facet = screen.getByRole("combobox", { name: "Filter by category" });
    await user.selectOptions(facet, "evening");
    await waitFor(() => {
      const last = client.viewQueries.at(-1);
      expect(JSON.stringify(last?.body.where ?? {})).toContain('"field":"category","op":"eq","value":"evening"');
    });
  });
});

describe("a second form on a tab", () => {
  it("starts folded to one line and opens on demand", async () => {
    const client = clientWithRows();
    const user = userEvent.setup();
    render(<ModulePage client={client} appId="log-1" onAsk={() => undefined} />);
    const folded = await screen.findByRole("region", { name: "Fix an entry by hand" });
    expect(within(folded).queryByRole("form")).not.toBeInTheDocument();
    await user.click(within(folded).getByRole("button", { name: "Open" }));
    expect(within(folded).getByRole("form", { name: "Fix an entry by hand" })).toBeInTheDocument();
    await user.click(within(folded).getByRole("button", { name: "Close" }));
    expect(within(folded).queryByRole("form")).not.toBeInTheDocument();
  });
});
