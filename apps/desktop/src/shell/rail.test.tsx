/** The sidebar folds to icons and remembers it; the assistant panel is closed on a module page
 *  until asked for, and that choice is remembered too. */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    await user.click(await screen.findByRole("button", { name: "New project" }));
    await user.click(await screen.findByRole("button", { name: /Import a project/ }));
    const input = document.querySelector('input[type="file"][accept=".alphamodule"]') as HTMLInputElement;
    expect(input).toBeTruthy();
    const file = new File(["zip-bytes"], "notes.alphamodule", { type: "application/zip" });
    await user.upload(input, file);
    expect(client.importedFiles).toEqual([file]);
    expect(await screen.findByRole("heading", { name: "Imported module" })).toBeInTheDocument();
  });
});

describe("New project", () => {
  it("shows only New project in the rail, not a separate New (module)", async () => {
    const client = new FakeWorkflowsClient();
    render(<App client={client} />);
    await screen.findByText("Runtime connected");
    expect(screen.getByRole("button", { name: "New project" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New module" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New" })).not.toBeInTheDocument();
  });

  it("opens a blank centre and asks what to accomplish, without making a project yet", async () => {
    const client = new FakeWorkflowsClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByText("Runtime connected");
    await user.click(screen.getByRole("button", { name: "New project" }));
    expect(await screen.findByText("What do you want to accomplish with this new project?")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Untitled project" })).toBeInTheDocument();
    // Nothing else on the page yet (no Alpha's notes / Modules / Sessions sections).
    expect(screen.queryByRole("heading", { name: "Alpha's notes" })).not.toBeInTheDocument();
    expect(client.projects.size).toBe(0);
  });

  it("makes the project only once the person answers, and moves the session onto it", async () => {
    const client = new FakeWorkflowsClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByText("Runtime connected");
    await user.click(screen.getByRole("button", { name: "New project" }));
    await screen.findByText("What do you want to accomplish with this new project?");
    expect(client.projects.size).toBe(0);
    const composer = screen.getByRole("textbox", { name: "Message" });
    await user.type(composer, "Plan the product launch");
    await user.click(screen.getByRole("button", { name: "Send" }));
    // The project page (not the blank draft) lands once Core has made the project.
    await screen.findByText("Alpha's notes");
    expect(client.projects.size).toBe(1);
    const [project] = [...client.projects.values()];
    expect(project.name).toBe("Untitled project");
    // The answer landed in the session now attached to the real project. The project page can
    // show before the send's answer renders, so wait for it rather than look once.
    expect(await within(screen.getByRole("complementary", { name: "Chief of Staff" })).findByText("Plan the product launch")).toBeInTheDocument();
  });
});

describe("the blank project page", () => {
  it("has Import and a Describe your project box whose text goes to the chat as the first message", async () => {
    const client = new FakeWorkflowsClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByText("Runtime connected");
    await user.click(screen.getByRole("button", { name: "New project" }));
    expect(await screen.findByRole("button", { name: /Import a project/ })).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "Describe your project" }), "Plan the product launch");
    await user.click(screen.getByRole("button", { name: "Start" }));
    await screen.findByText("Alpha's notes"); // the project page, once Core made the project
    expect(client.projects.size).toBe(1);
    expect(await within(screen.getByRole("complementary", { name: "Chief of Staff" })).findByText("Plan the product launch")).toBeInTheDocument();
  });
});

describe("deleting a project", () => {
  it("asks first, then removes it from the rail", async () => {
    const client = new FakeWorkflowsClient();
    await client.createProject("Untitled project");
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByText("Runtime connected");
    await user.click(await screen.findByRole("button", { name: "Untitled project options" }));
    await user.click(await screen.findByRole("menuitem", { name: "Delete" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Untitled project" })).not.toBeInTheDocument());
    expect(await client.listProjects()).toEqual([]);
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
