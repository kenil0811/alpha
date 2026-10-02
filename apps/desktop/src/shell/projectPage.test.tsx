/** The project page and its rail row: Rename, Change icon and Delete from both menus, the stored
 *  plan, and Core's own rename of an untitled project showing without a refresh. */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { FakeWorkflowsClient } from "../test/fakeWorkflows";

beforeEach(() => {
  window.localStorage.clear();
});

async function openProject(client: FakeWorkflowsClient, name: string) {
  const user = userEvent.setup();
  render(<App client={client} />);
  await user.click(await screen.findByRole("button", { name }));
  await screen.findByRole("heading", { name });
  return user;
}

describe("a project's rail menu", () => {
  it("offers Open, Rename, Change icon and Delete on right-click", async () => {
    const client = new FakeWorkflowsClient();
    await client.createProject("Launch");
    render(<App client={client} />);
    fireEvent.contextMenu((await screen.findByRole("button", { name: "Launch" })).closest(".navrow") as Element);
    expect(await screen.findByRole("menuitem", { name: "Open" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Rename" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Change icon" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Delete" })).toBeInTheDocument();
  });

  it("Rename saves the new name and the rail shows it", async () => {
    const client = new FakeWorkflowsClient();
    const project = await client.createProject("Launch");
    const user = userEvent.setup();
    render(<App client={client} />);
    await user.click(await screen.findByRole("button", { name: "Launch options" }));
    await user.click(await screen.findByRole("menuitem", { name: "Rename" }));
    const input = within(await screen.findByRole("dialog")).getByRole("textbox", { name: "Project name" });
    await user.clear(input);
    await user.type(input, "Product launch{Enter}");
    expect(await screen.findByRole("button", { name: "Product launch" })).toBeInTheDocument();
    expect(client.projects.get(project.project_id)?.name).toBe("Product launch");
  });

  it("Change icon stores the picked icon", async () => {
    const client = new FakeWorkflowsClient();
    const project = await client.createProject("Launch");
    const user = userEvent.setup();
    render(<App client={client} />);
    await user.click(await screen.findByRole("button", { name: "Launch options" }));
    await user.click(await screen.findByRole("menuitem", { name: "Change icon" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "megaphone" }));
    await waitFor(() => expect(client.projects.get(project.project_id)?.icon).toBe("megaphone"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("the project page", () => {
  it("has no New session button, and a … menu with Rename, Change icon and Delete", async () => {
    const client = new FakeWorkflowsClient();
    const project = await client.createProject("Launch");
    const user = await openProject(client, "Launch");
    expect(screen.queryByRole("button", { name: "Archive" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New session" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Project options" }));
    expect(await screen.findByRole("menuitem", { name: "Rename" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Change icon" })).toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(client.projects.get(project.project_id)?.archived_at).not.toBeNull());
  });

  it("shows Add goal instead of a helper sentence when there is no goal", async () => {
    const client = new FakeWorkflowsClient();
    await client.createProject("Launch");
    await openProject(client, "Launch");
    expect(screen.getByRole("button", { name: "Add goal" })).toBeInTheDocument();
    expect(screen.queryByText(/Add a goal:/)).not.toBeInTheDocument();
  });

  it("renders the stored plan above Alpha's notes", async () => {
    const client = new FakeWorkflowsClient();
    const project = await client.createProject("Launch");
    client.projectFiles.set(`${project.project_id}/plan.md`, "# Steps\n1. Pick a date\n- Book the venue");
    await openProject(client, "Launch");
    const plan = await screen.findByRole("region", { name: "Plan" });
    expect(within(plan).getByText("Steps")).toBeInTheDocument();
    expect(within(plan).getByText("Pick a date")).toBeInTheDocument();
    expect(within(plan).getByText("Book the venue")).toBeInTheDocument();
    expect(plan.compareDocumentPosition(screen.getByRole("heading", { name: /Alpha's notes/ })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("picks up Core's own rename of an untitled project, in the header and the rail", async () => {
    const client = new FakeWorkflowsClient();
    const project = await client.createProject("Untitled project");
    await openProject(client, "Untitled project");
    // Core names it after the first message, outside the page.
    client.projects.set(project.project_id, { ...project, name: "Product launch", icon: "megaphone" });
    expect(await screen.findByRole("heading", { name: "Product launch" }, { timeout: 5000 })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Product launch" })).toBeInTheDocument();
  }, 10_000);
});
