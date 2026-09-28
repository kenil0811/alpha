/** Every configurable setting is on the Settings page and a change is saved as it is made. */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { App } from "../App";
import { FakeWorkflowsClient } from "../test/fakeWorkflows";

describe("settings the person can change", () => {
  it("lists the models per stage and the build limits, and saves a change at once", async () => {
    const client = new FakeWorkflowsClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    expect(await screen.findByText("Runtime connected")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Settings" }));
    const models = await screen.findByLabelText("Models");
    const builder = within(models).getByLabelText("Model for building a new module");
    await user.selectOptions(builder, "sonnet");
    await waitFor(() => expect(client.settingsUpdates).toEqual([{ "models.builder_new": "sonnet" }]));
    expect(await screen.findByText(/^Saved\. Model for building a new module/)).toBeInTheDocument();

    // How long the checks' model thinks sits with the models; low by default.
    const effort = within(models).getByLabelText("Thinking for the checks");
    expect(effort).toHaveValue("low");
    await user.selectOptions(effort, "medium");
    await waitFor(() => expect(client.settingsUpdates.at(-1)).toEqual({ "effort.planner": "medium" }));

    const limits = screen.getByLabelText("Building limits");
    const minutes = within(limits).getByLabelText("Minutes per attempt");
    await user.clear(minutes);
    await user.type(minutes, "9");
    await waitFor(() => expect(client.settingsUpdates.at(-1)).toEqual({ "build.max_attempt_minutes": 9 }));
  });
});
