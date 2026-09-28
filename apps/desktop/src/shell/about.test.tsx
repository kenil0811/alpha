import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { FakeWorkflowsClient } from "../test/fakeWorkflows";
import { AboutYou } from "./AboutYou";

describe("About you", () => {
  it("lists facts with their source, takes a suggestion's yes, adds and forgets", async () => {
    const client = new FakeWorkflowsClient();
    client.facts = [{ fact_id: "fact_1", field: "degree", value: "MSc CS", provenance: "person", source: "person", confidence: 1, state: "accepted", recorded_at: "2026-09-28T10:00:00Z" }];
    client.suggestions = [{ fact_id: "fact_2", field: "skills", value: ["Python", "SQL"], provenance: "inferred", source: "academics", why: "from your coursework", confidence: 0.7, state: "suggested", recorded_at: "2026-09-28T10:00:00Z" }];
    const user = userEvent.setup();
    render(<AboutYou client={client} />);
    const table = await screen.findByRole("table", { name: "Facts about you" });
    expect(within(table).getByText("MSc CS")).toBeInTheDocument();
    expect(within(table).getByText("You said so")).toBeInTheDocument();
    expect(screen.getByText("Skills: Python, SQL")).toBeInTheDocument();
    expect(screen.getByText(/Alpha worked it out \(academics\) · from your coursework/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Yes, that's right" }));
    await waitFor(() => expect(client.factCalls).toEqual(["accept fact_2"]));
    expect(await within(table).findByText("Python, SQL")).toBeInTheDocument();

    await user.type(screen.getByLabelText("What"), "Target roles");
    await user.type(screen.getByLabelText("Value"), "backend, platform");
    await user.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(client.factCalls).toContain("add target_roles"));
    expect(await within(table).findByText("backend, platform")).toBeInTheDocument();

    await user.click(within(table).getByRole("button", { name: "Forget Degree" }));
    await waitFor(() => expect(within(table).queryByText("MSc CS")).not.toBeInTheDocument());
  });
});
