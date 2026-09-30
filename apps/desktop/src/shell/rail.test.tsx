/** The sidebar folds to icons and remembers it; the assistant panel is closed on a module page
 *  until asked for, and that choice is remembered too. */
import { fireEvent, render, screen } from "@testing-library/react";
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

describe("a module's context menu", () => {
  it("opens on right-click with Open, Hide from sidebar, Export… and Delete", async () => {
    const client = new FakeWorkflowsClient();
    client.apps = [sampleSummary()];
    client.details.set("notes-list-1a2b3c", sampleDetail());
    render(<App client={client} />);
    const row = (await screen.findByRole("button", { name: "Notes list" })).closest(".navrow");
    expect(row).toBeTruthy();
    fireEvent.contextMenu(row as Element);
    expect(await screen.findByRole("menuitem", { name: "Open" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Hide from sidebar" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Export…" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Delete" })).toBeInTheDocument();
  });

  it("Export… exports the module's current source", async () => {
    const client = new FakeWorkflowsClient();
    client.apps = [sampleSummary()];
    client.details.set("notes-list-1a2b3c", sampleDetail());
    const originalCreate = URL.createObjectURL;
    const originalRevoke = URL.revokeObjectURL;
    URL.createObjectURL = () => "blob:mock";
    URL.revokeObjectURL = () => {};
    try {
      const user = userEvent.setup();
      render(<App client={client} />);
      await user.click(await screen.findByRole("button", { name: "Notes list options" }));
      await user.click(await screen.findByRole("menuitem", { name: "Export…" }));
      expect(client.exportedModules).toEqual(["notes-list-1a2b3c"]);
    } finally {
      URL.createObjectURL = originalCreate;
      URL.revokeObjectURL = originalRevoke;
    }
  });

  it("Delete asks first, then removes the module and leaves the page", async () => {
    const client = new FakeWorkflowsClient();
    client.apps = [sampleSummary()];
    client.details.set("notes-list-1a2b3c", sampleDetail());
    const user = userEvent.setup();
    render(<App client={client} />);
    await user.click(await screen.findByRole("button", { name: "Notes list options" }));
    await user.click(await screen.findByRole("menuitem", { name: "Delete" }));
    expect(await screen.findByText("Delete Notes list?")).toBeInTheDocument();
    expect(client.removed).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(client.removed).toEqual(["notes-list-1a2b3c"]);
    expect(screen.queryByText("Delete Notes list?")).not.toBeInTheDocument();
  });
});

describe("adding a module from a file", () => {
  it("installs the file through Core and opens the new module", async () => {
    const client = new FakeWorkflowsClient();
    client.importResult = { app_id: "imported-1", name: "Imported module" };
    client.details.set("imported-1", sampleDetail({ app_id: "imported-1", name: "Imported module" }));
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByText("Runtime connected");
    await user.click(screen.getByRole("button", { name: "New module" }));
    await user.click(await screen.findByRole("menuitem", { name: "Add a module from a file…" }));
    const input = document.querySelector('input[type="file"][accept=".alphamodule"]') as HTMLInputElement;
    expect(input).toBeTruthy();
    const file = new File(["zip-bytes"], "notes.alphamodule", { type: "application/zip" });
    await user.upload(input, file);
    expect(client.importedFiles).toEqual([file]);
    expect(await screen.findByRole("heading", { name: "Imported module" })).toBeInTheDocument();
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
