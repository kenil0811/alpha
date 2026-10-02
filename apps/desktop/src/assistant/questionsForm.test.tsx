/** Discovery questions take several picks per question plus the person's own words. */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { QuestionsForm } from "./QuestionsForm";

describe("QuestionsForm", () => {
  it("joins several picks and free text into one answer per question", async () => {
    const onAnswer = vi.fn();
    const user = userEvent.setup();
    render(
      <QuestionsForm
        questions={[
          { id: "role", question: "Who will use it?", options: ["Professor", "Researcher"], why_it_matters: "Decides what it tracks." },
          { id: "tools", question: "What do you use today?", options: ["Canvas", "Excel"], why_it_matters: "Decides the sources." },
        ]}
        busy={false}
        onAnswer={onAnswer}
        onDefaults={() => undefined}
      />,
    );
    await user.click(screen.getByRole("checkbox", { name: "Professor" }));
    await user.click(screen.getByRole("checkbox", { name: "Researcher" }));
    await user.click(screen.getByRole("checkbox", { name: "Canvas" }));
    await user.type(screen.getByRole("textbox", { name: "Your own answer for: What do you use today?" }), "Zotero");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(onAnswer).toHaveBeenCalledWith({ role: "Professor; Researcher", tools: "Canvas; Zotero" });
  });
});
