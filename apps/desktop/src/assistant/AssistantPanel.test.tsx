import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    await user.type(screen.getByLabelText("Message"), "Track what I eat");
    await user.click(screen.getByRole("button", { name: "Send" }));

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
    await user.type(screen.getByLabelText("Message"), "Track what I eat");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByRole("form", { name: "A few questions" });
    await user.click(screen.getByRole("button", { name: "Use these defaults for now" }));
    await waitFor(() => expect(screen.getByLabelText("What Alpha understood")).toHaveTextContent("Understanding 2"));
    // The brief is shown and nothing is made yet: what the person types next refines it.
    await user.type(screen.getByLabelText("Message"), "also track protein");
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
    await user.type(screen.getByLabelText("Message"), "anything");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not work this out");
  });
});

describe("the brief says where data goes", () => {
  it("shows Core's statement under the brief", async () => {
    const client = scriptedTracker();
    const base = client.assistantScript!;
    const notice = "Your records and files are stored on this Mac. What you type to the assistant is sent to Anthropic's Claude service over the internet.";
    client.assistantScript = (c, r) => ({ ...base(c, r), data_notice: notice });
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByRole("status");
    await user.type(screen.getByLabelText("Message"), "Track what I eat");
    await user.click(screen.getByRole("button", { name: "Send" }));
    const brief = await screen.findByLabelText("What Alpha understood");
    expect(brief).toHaveTextContent(`Where your data goes: ${notice}`);
  });
});

describe("a turn that takes long", () => {
  it("shows how long it has been thinking and lets the person stop it", async () => {
    const client = new FakeCoreClient();
    client.assistantScript = (c: Conversation, reply: ConversationReply | null): Conversation => (reply === null ? { ...c, state: "thinking" } : c);
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByRole("status");
    await user.type(screen.getByLabelText("Message"), "Plan my week");
    await user.click(screen.getByRole("button", { name: "Send" }));
    const waiting = await screen.findByText(/Thinking about your request/);
    expect(waiting).toHaveTextContent(/0:0\d/);
    await user.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(client.cancelled).toEqual(["conv_1"]));
    expect(await screen.findByRole("alert", { name: "Alpha could not work this out" })).toHaveTextContent("You stopped it");
  });

  it("shows the shaped options after Alpha looked around, and the choice becomes the reply", async () => {
    const client = new FakeCoreClient();
    const proposal = {
      intro: "Two shapes; the fuller one is what I'd build for you.",
      options: [
        { id: "lean", title: "Just the list", summary: "A notes table with a quick add box.", why: "Fastest to start." },
        { id: "full", title: "List with tags", summary: "The list plus tags, a done flag and a weekly count.", why: "What most people want." },
      ],
      default: "full",
      evidence: [{ kind: "search", title: "How people keep notes", url: "https://example.com/notes", note: "Title, date, tags." }],
    };
    client.assistantScript = (c: Conversation, reply: ConversationReply | null): Conversation =>
      reply === null ? { ...c, state: "proposed", delivery: "app", current_brief: sampleBrief(), proposal } : { ...c, state: "briefed", delivery: "app", current_brief: sampleBrief() };
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByRole("status");
    await user.type(screen.getByLabelText("Message"), "Keep a notes list");
    await user.click(screen.getByRole("button", { name: "Send" }));
    const card = await screen.findByLabelText("Options");
    expect(within(card).getByText("List with tags")).toBeInTheDocument();
    expect(within(card).getByText("Alpha's pick")).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "What Alpha looked at (1)" }));
    expect(within(card).getByRole("link", { name: "How people keep notes" })).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Go with this" }));
    await waitFor(() => expect(String(client.conversations.get("conv_1")?.turns.at(-1)?.content.text)).toMatch(/^Go with "List with tags"/));
    await waitFor(() => expect(screen.queryByLabelText("Options")).not.toBeInTheDocument());
  });
});

describe("attaching context to a message", () => {
  it("a pasted image becomes a removable chip, is sent with the message, and shows in history", async () => {
    const client = scriptedTracker();
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByRole("status");
    const box = screen.getByLabelText("Message");
    const file = new File(["fake-bytes"], "screenshot.png", { type: "image/png" });
    fireEvent.paste(box, { clipboardData: { items: [{ getAsFile: () => file }] } });
    expect(await screen.findByText("screenshot.png")).toBeInTheDocument();

    await user.type(box, "what does this show?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    // The attachment travelled with the message and is not left queued in the composer.
    await waitFor(() => expect(screen.getAllByText("screenshot.png")).toHaveLength(1));
    expect(within(screen.getByText("screenshot.png").closest(".msg--user")!).getByText("screenshot.png")).toBeInTheDocument();
  });

  it("removing a queued attachment before sending leaves it out of the message", async () => {
    const client = scriptedTracker();
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByRole("status");
    const box = screen.getByLabelText("Message");
    const file = new File(["x"], "notes.txt", { type: "text/plain" });
    fireEvent.paste(box, { clipboardData: { items: [{ getAsFile: () => file }] } });
    await screen.findByText("notes.txt");
    await user.click(screen.getByRole("button", { name: "Remove notes.txt" }));
    expect(screen.queryByText("notes.txt")).not.toBeInTheDocument();

    await user.type(box, "just text, no attachment");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("just text, no attachment");
    expect(screen.queryByText("notes.txt")).not.toBeInTheDocument();
  });
});
