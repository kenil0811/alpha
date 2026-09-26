/**
 * M1 review finding F03 (repair task M1-R04), on a real generated manifest: the G1 held-out
 * planner (converted unchanged from the G1 evidence). A person pastes a multi-line list, gives
 * the hours, runs one action and reads the plan, without JSON or choosing internal steps.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ActionSummary } from "../core/client";
import dayplan from "../test/fixtures/dayplan-app.json";
import { FakeWorkflowsClient, sampleDetail } from "../test/fakeWorkflows";
import { Workspace } from "./Workspace";

const actions = dayplan.actions as unknown as ActionSummary[];
const LIST = "Finish quarterly report 2h\nCall the bank 20m\nReview Asha's pull request 45m\nGroceries 1h\nBook dentist appointment\nClean out email inbox 1.5h";

function client(primary: string | null) {
  const c = new FakeWorkflowsClient();
  c.details.set(dayplan.app_id, sampleDetail({ app_id: dayplan.app_id, name: dayplan.name, ui: null, actions, collections: [], primary_action: primary }));
  c.actionOutput = dayplan.fit_plan_output as Record<string, unknown>;
  return c;
}

describe("a generated App without its own screen", () => {
  it("leads with its main action, takes a pasted list and shows the plan in plain form", async () => {
    const fake = client("fit_plan");
    const user = userEvent.setup();
    render(<Workspace client={fake} appId={dayplan.app_id} onBack={() => undefined} />);

    const main = await screen.findByRole("form", { name: "Fit my list into today's hours" });
    const list = within(main).getByLabelText("List");
    expect(list.tagName).toBe("TEXTAREA");
    await user.type(list, LIST.replace(/\n/g, "{Enter}"));
    await user.type(within(main).getByLabelText("Hours available"), "4");
    await user.click(within(main).getByRole("button", { name: "Run" }));

    expect(fake.invocations).toEqual([
      { appId: dayplan.app_id, actionId: "fit_plan", input: { list: LIST, hours_available: 4 }, origin: "user" },
    ]);
    const result = await within(main).findByRole("status");
    expect(result).toHaveTextContent("Done.");
    const tables = within(result).getAllByRole("table");
    const plan = tables.find((t) => within(t).queryByText("Running minutes"))!;
    expect(within(plan).getByText("Finish quarterly report")).toBeInTheDocument();
    expect(within(plan).getByText("Book dentist appointment")).toBeInTheDocument();
    const wontFit = tables.find((t) => within(t).queryByText("Groceries") && !within(t).queryByText("Running minutes"))!;
    expect(within(wontFit).getByText("Clean out email inbox")).toBeInTheDocument();
    expect(result).toHaveTextContent("Minutes spare25");
    // No raw data for the person to decode.
    expect(result.textContent).not.toMatch(/[{}[\]"]/);

    // The other step a person could run stays reachable, but out of the way; the report step,
    // which needs another step's structured output, is not offered as a form at all.
    expect(screen.getByText("More actions (1)")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Write up the plan to read" })).not.toBeInTheDocument();
    expect(screen.getByText(/One more step runs inside this workflow/)).toBeInTheDocument();
  });

  it("never asks a person to type structured data, even without a declared main action", async () => {
    render(<Workspace client={client(null)} appId={dayplan.app_id} onBack={() => undefined} />);
    await screen.findByRole("form", { name: "Fit my list into today's hours" });
    expect(screen.getByRole("form", { name: "Read my pasted to-do list" })).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Write up the plan to read" })).not.toBeInTheDocument();
    for (const box of screen.getAllByRole("textbox")) {
      expect(box.getAttribute("placeholder") ?? "").not.toMatch(/json/i);
    }
  });
});
