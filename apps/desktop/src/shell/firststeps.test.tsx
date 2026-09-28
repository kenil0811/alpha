import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { FakeWorkflowsClient } from "../test/fakeWorkflows";
import { FirstSteps, Noticed } from "./Home";

describe("first steps", () => {
  it("asks the five questions once and turns the answers into a proposed start", async () => {
    const client = new FakeWorkflowsClient();
    client.onboardingState = { ...client.onboardingState, done: false };
    const started: string[] = [];
    const user = userEvent.setup();
    render(<FirstSteps client={client} onStart={(r) => started.push(r)} />);
    const form = await screen.findByRole("form", { name: "First steps" });
    await user.type(within(form).getByLabelText("What do you do?"), "MSc student");
    await user.type(within(form).getByLabelText("What are you trying to get better at right now?"), "a backend job");
    await user.click(within(form).getByRole("button", { name: "Propose where to begin" }));
    expect(client.onboardingAnswers).toEqual({ occupation: "MSc student", goal: "a backend job" });
    const card = await screen.findByLabelText("Where to begin");
    expect(within(card).getByText("Coursework")).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Start with this" }));
    expect(started).toEqual(["Keep a list of my courses with assignments"]);
  });

  it("stays out of the way once done", async () => {
    const client = new FakeWorkflowsClient();
    const { container } = render(<FirstSteps client={client} onStart={() => undefined} />);
    await new Promise((r) => setTimeout(r, 20));
    expect(container).toBeEmptyDOMElement();
  });

  it("shows what Alpha noticed with a next step and a dismissal", async () => {
    const client = new FakeWorkflowsClient();
    client.nudgeRows = [{ nudge_id: "nudge_1", text: "Your notes list has stayed empty.", next_step: "Add my first three notes", created_at: "" }];
    const started: string[] = [];
    const user = userEvent.setup();
    render(<Noticed client={client} onStart={(r) => started.push(r)} />);
    const card = await screen.findByLabelText("Alpha noticed");
    await user.click(within(card).getByRole("button", { name: "Add my first three notes" }));
    expect(started).toEqual(["Add my first three notes"]);
    await user.click(within(card).getByRole("button", { name: "Dismiss" }));
    expect(client.dismissed).toEqual(["nudge_1"]);
  });
});
