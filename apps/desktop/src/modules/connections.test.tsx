import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { FakeWorkflowsClient, sampleDetail } from "../test/fakeWorkflows";
import { ModulePage } from "./ModulePage";

describe("connections between modules", () => {
  it("shows each declared use in Settings with a switch", async () => {
    const fake = new FakeWorkflowsClient();
    fake.details.set("notes-list-1a2b3c", sampleDetail({ uses: [{ module: "academics", views: ["courses.all"], purpose: "The notes cite courses." }] }));
    fake.connectionRows = [{ module: "academics", name: "Academics", purpose: "The notes cite courses.", views: [{ id: "courses.all", collection: "courses", kind: "records" }], enabled: true, installed: true }];
    const user = userEvent.setup();
    render(<ModulePage client={fake} appId="notes-list-1a2b3c" onAsk={() => undefined} />);
    await screen.findByRole("heading", { name: "Notes list" });
    await user.click(screen.getByRole("tab", { name: "Settings" }));
    const list = await screen.findByLabelText("Connections");
    expect(within(list).getByText("Academics")).toBeInTheDocument();
    expect(within(list).getByText(/The notes cite courses\. · courses/)).toBeInTheDocument();
    const toggle = within(list).getByRole("button", { name: "On" });
    await user.click(toggle);
    await waitFor(() => expect(within(list).getByRole("button", { name: "Off" })).toHaveAttribute("aria-pressed", "false"));
    expect(fake.connectionRows[0].enabled).toBe(false);
  });

  it("shows a related record by its title and lets the person pick another", async () => {
    const fake = new FakeWorkflowsClient();
    fake.details.set(
      "notes-list-1a2b3c",
      sampleDetail({
        uses: [{ module: "academics", views: ["courses.all"], purpose: "The notes cite courses." }],
        collections: [{ name: "notes", fields: [{ name: "title", kind: "text" }, { name: "course", kind: "relation", module: "academics", collection: "courses" }] }],
      }),
    );
    fake.related["academics/courses"] = [
      { id: "rec_c1", title: "Distributed systems", values: {} },
      { id: "rec_c2", title: "Databases", values: {} },
    ];
    fake.records.set("notes-list-1a2b3c/notes", [{ id: "rec_1", revision: 1, values: { title: "Revise", course: "rec_c1" }, created_at: "", updated_at: "" }]);
    const user = userEvent.setup();
    render(<ModulePage client={fake} appId="notes-list-1a2b3c" onAsk={() => undefined} />);
    const table = await screen.findByRole("table");
    expect(await within(table).findByText("Distributed systems")).toBeInTheDocument();
    await user.click(within(table).getByText("Distributed systems"));
    await user.selectOptions(await within(table).findByRole("combobox", { name: "Course" }), "rec_c2");
    await waitFor(() => expect(fake.mutations[0]).toMatchObject({ op: "correct", changes: { course: "rec_c2" } }));
  });
});
