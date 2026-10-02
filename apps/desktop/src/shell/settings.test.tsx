/** Every configurable setting is on the Settings page and a change is saved as it is made. */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { App } from "../App";
import { FakeWorkflowsClient } from "../test/fakeWorkflows";

describe("settings the person can change", () => {
  it("keeps model choice on the provider rows, lists thinking and build limits, and saves at once", async () => {
    const client = new FakeWorkflowsClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    expect(await screen.findByText("Runtime connected")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Settings" }));
    const models = await screen.findByLabelText("Models");
    // The per-stage model lists would repeat the Claude row's model list.
    expect(within(models).queryByLabelText("Model for building a new project")).not.toBeInTheDocument();
    const thinking = within(models).getByLabelText("Thinking for the checks");
    await user.selectOptions(thinking, "high");
    await waitFor(() => expect(client.settingsUpdates).toEqual([{ "effort.planner": "high" }]));
    expect(await screen.findByText(/^Saved\. Thinking for the checks/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Builds" }));
    const limits = screen.getByLabelText("Building limits");
    const minutes = within(limits).getByLabelText("Minutes per attempt");
    await user.clear(minutes);
    await user.type(minutes, "9");
    await waitFor(() => expect(client.settingsUpdates.at(-1)).toEqual({ "build.max_attempt_minutes": 9 }));
  });
});
