import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { App } from "../App";
import { FakeCoreClient, sampleBrief } from "../test/fakeClient";
import type { Conversation, ConversationReply } from "../core/client";

const TECHNICAL = /\b(sql|schema|json|database|api|component|framework|endpoint|payload)\b/i;

function scriptedTracker(): FakeCoreClient {
  const client = new FakeCoreClient();
  client.assistantScript = (c: Conversation, reply: ConversationReply | null): Conversation => {
    if (reply === null) {
      return {
        ...c,
        state: "waiting_for_user",
        delivery: "app",
        interpretation: {
          outcome: "A personal food diary with calories, daily totals, history and a trend.",
          main_input: "Short food entries typed as you eat, with how much.",
          useful_result: "Today's total, an editable history and a week-over-week trend.",
          important_assumptions: ["Single user on this Mac"],
        },
        reply: "I can make a small food diary you keep on this Mac. Two quick questions first.",
        questions: [
          {
            id: "portion",
            question: "How do you want to enter how much you ate?",
            options: ["Rough portions (small/medium/large)", "Grams or millilitres"],
            why_it_matters: "It changes how calories are estimated.",
          },
        ],
        current_brief: sampleBrief({ revision: 1, open_questions: [{ id: "portion", question: "How do you want to enter how much you ate?", options: [], why_it_matters: "x" }], assumptions: [{ text: "Single user on this Mac", source: "model_default", turn_ref: null }] }),
      };
    }
    const chosen = reply.answers?.portion ?? (reply.use_defaults ? "Rough portions (default)" : reply.text ?? "");
    return {
      ...c,
      state: "briefed",
      questions: [],
      reply: `Got it: ${chosen}. I'll make the food diary.`,
      current_brief: sampleBrief({
        revision: (c.current_brief?.revision ?? 1) + 1,
        supersedes_revision: c.current_brief?.revision ?? 1,
        assumptions: [
          { text: "Single user on this Mac", source: "model_default", turn_ref: null },
          { text: `Portions: ${chosen}`, source: reply.text ? "user_correction" : "user_answer", turn_ref: "t2" },
        ],
      }),
    };
  };
  return client;
}

describe("assistant surface", () => {
  it("shows the interpretation, asks a question with options and records the answer as the user's", async () => {
    const client = scriptedTracker();
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByRole("status");
    await user.type(screen.getByLabelText("What do you want done?"), "Track what I eat");
    await user.click(screen.getByRole("button", { name: "Ask Alpha" }));

    const understood = await screen.findByLabelText("How Alpha understood it");
    expect(understood).toHaveTextContent("A personal food diary");
    expect(screen.getByText(/Two quick questions first/)).toBeInTheDocument();
    const form = screen.getByRole("form", { name: "A few questions" });
    expect(within(form).getByText("How do you want to enter how much you ate?")).toBeInTheDocument();
    await user.click(within(form).getByLabelText("Grams or millilitres"));
    await user.click(within(form).getByRole("button", { name: "Continue" }));

    await waitFor(() => expect(screen.getByText(/Got it: Grams or millilitres/)).toBeInTheDocument());
    const brief = screen.getByLabelText("What Alpha understood");
    expect(brief).toHaveTextContent("a reusable tool you can keep using");
    expect(brief).toHaveTextContent("Portions: Grams or millilitres");
    expect(brief).toHaveTextContent("you chose");
    expect(brief).toHaveTextContent("Understanding 2");
    expect(brief).toHaveTextContent("keeping your entries and history");
    expect(brief.textContent).not.toMatch(TECHNICAL);
    expect(screen.queryByRole("form", { name: "A few questions" })).not.toBeInTheDocument();
  });

  it("lets the user accept defaults and later correct the brief in their own words", async () => {
    const client = scriptedTracker();
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByRole("status");
    await user.type(screen.getByLabelText("What do you want done?"), "Track what I eat");
    await user.click(screen.getByRole("button", { name: "Ask Alpha" }));
    await screen.findByRole("form", { name: "A few questions" });
    await user.click(screen.getByRole("button", { name: "Use these defaults for now" }));
    await waitFor(() => expect(screen.getByLabelText("What Alpha understood")).toHaveTextContent("Understanding 2"));
    await user.type(screen.getByLabelText("Change or add something"), "also track protein");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(screen.getByLabelText("What Alpha understood")).toHaveTextContent("Understanding 3"));
    expect(screen.getByLabelText("What Alpha understood")).toHaveTextContent("you corrected");
  });

  it("explains a failed turn honestly and offers to start over", async () => {
    const client = new FakeCoreClient();
    client.assistantScript = (c) => ({ ...c, state: "failed", error: "the assistant did not answer in time" });
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByRole("status");
    await user.type(screen.getByLabelText("What do you want done?"), "anything");
    await user.click(screen.getByRole("button", { name: "Ask Alpha" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not work this out");
  });
});
