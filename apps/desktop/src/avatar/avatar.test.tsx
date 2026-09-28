import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ActClient, ActTurn } from "../core/client";
import { AvatarWindow, HANDOFF_KEY } from "./AvatarWindow";

class FakeAct implements ActClient {
  asked: string[] = [];
  next: Partial<ActTurn> = {};
  async act(text: string): Promise<ActTurn> {
    this.asked.push(text);
    return {
      turn_id: `act_${this.asked.length}`,
      text,
      kind: "run",
      app_id: "diet",
      app_name: "Daily Diet Tracker",
      action_id: "log_food",
      run_id: "run_1",
      conversation_id: null,
      open: null,
      reply: "Logged two eggs: 156 calories, 1,240 so far today.",
      created_at: new Date().toISOString(),
      ...this.next,
    };
  }
  async recentActs(): Promise<ActTurn[]> {
    return [];
  }
}

describe("the desktop avatar", () => {
  it("opens from the character, does what it is told and says what happened", async () => {
    const client = new FakeAct();
    const layouts: boolean[] = [];
    const user = userEvent.setup();
    render(<AvatarWindow client={client} host={{ layout: async (e) => void layouts.push(e), showMain: async () => undefined }} />);
    await user.click(screen.getByRole("button", { name: "Ask Alpha" }));
    expect(layouts).toEqual([true]);
    await user.type(await screen.findByLabelText("What should Alpha do"), "log two eggs");
    await user.click(screen.getByRole("button", { name: "Do it" }));
    expect(client.asked).toEqual(["log two eggs"]);
    expect(await screen.findByText(/Logged two eggs: 156 calories/)).toBeInTheDocument();
    expect(screen.getByText(/Daily Diet Tracker/)).toBeInTheDocument();
  });

  it("hands a module over to the main window and brings it forward", async () => {
    const client = new FakeAct();
    client.next = { kind: "open", open: { app_id: "diet", tab_id: "today" }, reply: "Opening Daily Diet Tracker." };
    let shown = 0;
    const user = userEvent.setup();
    render(<AvatarWindow client={client} host={{ layout: async () => undefined, showMain: async () => void (shown += 1) }} />);
    await user.click(screen.getByRole("button", { name: "Ask Alpha" }));
    await user.type(await screen.findByLabelText("What should Alpha do"), "open my diet tracker{enter}");
    await screen.findByText("Opening Daily Diet Tracker.");
    expect(shown).toBe(1);
    expect(JSON.parse(localStorage.getItem(HANDOFF_KEY) ?? "{}")).toMatchObject({ app_id: "diet", tab_id: "today" });
  });
});
