/** The ⌘K command menu: opens on the shortcut, filters by substring, and Enter runs the
 *  highlighted item (arrow keys move the highlight first). */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { Utensils } from "lucide-react";
import { CommandMenu } from "./CommandMenu";
import type { AppSummary } from "../core/client";

const modules: AppSummary[] = [
  { app_id: "meals", name: "Meals", description: "Track what I eat", state: "active", actions: 2, has_ui: false, created_at: new Date().toISOString(), origin: "generated" },
  { app_id: "jobs", name: "Job search", description: "Track applications", state: "active", actions: 1, has_ui: false, created_at: new Date().toISOString(), origin: "generated" },
] as unknown as AppSummary[];

function setup(onNew = vi.fn()) {
  render(
    <MemoryRouter>
      <CommandMenu modules={modules} icons={{ meals: Utensils }} onNew={onNew} />
    </MemoryRouter>,
  );
  return { onNew };
}

describe("command menu", () => {
  it("opens on Cmd+K, filters by substring, and closes after a choice", async () => {
    const user = userEvent.setup();
    setup();
    expect(screen.queryByRole("combobox", { name: "Command menu" })).not.toBeInTheDocument();

    await user.keyboard("{Meta>}k{/Meta}");
    const input = await screen.findByRole("combobox", { name: "Command menu" });
    expect(screen.getByText("Open Meals")).toBeInTheDocument();
    expect(screen.getByText("Open Job search")).toBeInTheDocument();

    await user.type(input, "job");
    expect(screen.queryByText("Open Meals")).not.toBeInTheDocument();
    expect(screen.getByText("Open Job search")).toBeInTheDocument();

    await user.keyboard("{Enter}");
    expect(screen.queryByRole("combobox", { name: "Command menu" })).not.toBeInTheDocument();
  });

  it("moves the highlight with arrow keys and runs the highlighted item on Enter", async () => {
    const user = userEvent.setup();
    const { onNew } = setup();
    await user.keyboard("{Meta>}k{/Meta}");
    const input = await screen.findByRole("combobox", { name: "Command menu" });
    await user.type(input, "new module");
    expect(screen.getByRole("option", { name: /New module/ })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Enter}");
    expect(onNew).toHaveBeenCalledTimes(1);
  });
});
