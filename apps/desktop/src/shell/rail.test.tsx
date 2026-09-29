/** The sidebar folds to icons and remembers it; the assistant panel is closed on a module page
 *  until asked for, and that choice is remembered too. */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { FakeWorkflowsClient, sampleDetail, sampleSummary } from "../test/fakeWorkflows";

beforeEach(() => {
  window.localStorage.clear();
});

describe("the sidebar", () => {
  it("collapses to icons, keeps every destination reachable, and remembers the choice", async () => {
    const user = userEvent.setup();
    render(<App client={new FakeWorkflowsClient()} />);
    expect(await screen.findByText("Runtime connected")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Collapse the sidebar" }));
    const rail = screen.getByRole("navigation", { name: "Alpha" });
    expect(rail).toHaveClass("rail--collapsed");
    expect(screen.getByRole("button", { name: "Settings" })).toHaveAttribute("title", "Settings");
    expect(window.localStorage.getItem("alpha.rail.collapsed")).toBe("1");
    await user.click(screen.getByRole("button", { name: "Expand the sidebar" }));
    expect(rail).not.toHaveClass("rail--collapsed");
  });
});

describe("the assistant panel on a module page", () => {
  it("is closed until asked for, and reopens on Home", async () => {
    const client = new FakeWorkflowsClient();
    client.apps = [sampleSummary()];
    client.details.set("notes-list-1a2b3c", sampleDetail());
    const user = userEvent.setup();
    render(<App client={client} />);
    expect(await screen.findByText("Runtime connected")).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Chief of Staff" })).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Notes list" }));
    await screen.findByRole("heading", { name: "Notes list" });
    expect(screen.queryByRole("complementary", { name: "Chief of Staff" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Home" }));
    expect(await screen.findByRole("complementary", { name: "Chief of Staff" })).toBeInTheDocument();
  });
});
