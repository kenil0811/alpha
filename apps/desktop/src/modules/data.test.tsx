/** The derived page: every table a module keeps, editable by the person as their own change. */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { FakeWorkflowsClient, sampleDetail } from "../test/fakeWorkflows";
import { ModulePage } from "./ModulePage";

function client(): FakeWorkflowsClient {
  const fake = new FakeWorkflowsClient();
  fake.details.set("notes-list-1a2b3c", sampleDetail({ record_counts: { notes: 2 } }));
  fake.records.set("notes-list-1a2b3c/notes", [
    { id: "rec_1", revision: 1, values: { title: "Buy milk", calories: 120 }, provenance: { calories: { source: "model_estimate" } }, created_at: "", updated_at: "" },
    { id: "rec_2", revision: 3, values: { title: "Call Ravi", calories: null }, created_at: "", updated_at: "" },
  ]);
  return fake;
}

describe("a derived table page", () => {
  it("shows each table, corrects a cell as the person's change and removes a row", async () => {
    const fake = client();
    const user = userEvent.setup();
    render(<ModulePage client={fake} appId="notes-list-1a2b3c" onAsk={() => undefined} />);
    await screen.findByRole("heading", { name: "Notes list" });
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Buy milk")).toBeInTheDocument();
    expect(within(table).getByLabelText("estimate")).toHaveAttribute("title", expect.stringContaining("estimate"));

    await user.click(within(table).getAllByText("120")[0]);
    const input = within(table).getByRole("spinbutton", { name: "Calories" });
    await user.clear(input);
    await user.type(input, "95{Enter}");
    await waitFor(() => expect(fake.mutations[0]).toMatchObject({ op: "correct", collection: "notes", id: "rec_1", expected_revision: 1, changes: { calories: 95 } }));
    expect((await within(table).findAllByText("95")).length).toBeGreaterThan(0);

    await user.click(within(table).getByRole("row", { name: "Open Call Ravi" }));
    await user.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(fake.mutations[1]).toMatchObject({ op: "delete", id: "rec_2", expected_revision: 3 }));
    await waitFor(() => expect(within(table).queryByText("Call Ravi")).not.toBeInTheDocument());
  });

  it("adds a row from a form built from the table's fields", async () => {
    const fake = client();
    const user = userEvent.setup();
    render(<ModulePage client={fake} appId="notes-list-1a2b3c" onAsk={() => undefined} />);
    await screen.findByRole("heading", { name: "Notes list" });
    await user.click(await screen.findByRole("button", { name: "Add" }));
    const form = screen.getByRole("form", { name: "Add to Notes" });
    await user.type(within(form).getByLabelText("Title"), "Water the plants");
    await user.type(within(form).getByLabelText("Calories (optional)"), "0");
    await user.click(within(form).getByRole("button", { name: "Add" }));
    await waitFor(() => expect(fake.mutations[0]).toMatchObject({ op: "create", collection: "notes", values: { title: "Water the plants", calories: 0 } }));
    expect(await screen.findByText("Water the plants")).toBeInTheDocument();
  });
});
