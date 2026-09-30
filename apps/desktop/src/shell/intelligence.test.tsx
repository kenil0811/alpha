import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FakeWorkflowsClient } from "../test/fakeWorkflows";
import { Intelligence } from "./Intelligence";

function setup() {
  const client = new FakeWorkflowsClient();
  client.facts = [{ fact_id: "fact_1", field: "occupation", value: "founder", provenance: "person", source: "person", confidence: 1, state: "accepted", recorded_at: "2026-09-28T10:00:00Z" }];
  const modules = [
    { app_id: "jobs", name: "Job profile", description: "Roles and a resume.", origin: "created" as const, state: "active", has_ui: true, actions: 2, current_version_id: "v1", current_release_id: "r1", created_at: "", updated_at: "" },
    { app_id: "academics", name: "Academics", description: "Courses and grades.", origin: "created" as const, state: "active", has_ui: true, actions: 1, current_version_id: "v1", current_release_id: "r1", created_at: "", updated_at: "" },
  ];
  client.connectionRows = [{ module: "academics", name: "Academics", purpose: "to list your courses on the resume", views: [{ id: "courses.all", collection: "courses", kind: null }], enabled: true, installed: true }];
  client.scheduleRows = { jobs: [{ id: "daily", title: "Look for new roles", action: "scan", when: "every day at 09:00", enabled: true, last_run_at: null, last_run_id: null, last_error: null, next_run_at: null }] };
  const onOpenModule = vi.fn();
  const onOpenAbout = vi.fn();
  render(<Intelligence client={client} modules={modules} icons={{}} onOpenModule={onOpenModule} onOpenAbout={onOpenAbout} />);
  return { client, onOpenModule, onOpenAbout };
}

describe("Intelligence", () => {
  it("shows the second brain as a graph of every module and fact, opening what you click", async () => {
    const { onOpenAbout, onOpenModule } = setup();
    const graph = await screen.findByRole("img", { name: "Second brain graph" });
    expect(await within(graph).findByText("Occupation: founder")).toBeInTheDocument();
    expect(within(graph).getByText("Job profile")).toBeInTheDocument();
    expect(within(graph).getByText("Academics")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Manage what Alpha knows" }));
    expect(onOpenAbout).toHaveBeenCalled();
    await user.click(within(graph).getByText("Job profile"));
    expect(onOpenModule).toHaveBeenCalledWith("jobs");
  });

  it("shows an honest empty state with no modules and no facts", async () => {
    const client = new FakeWorkflowsClient();
    const onOpenModule = vi.fn();
    const onOpenAbout = vi.fn();
    render(<Intelligence client={client} modules={[]} icons={{}} onOpenModule={onOpenModule} onOpenAbout={onOpenAbout} />);
    expect(await screen.findByText(/Nothing yet/)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Second brain graph" })).not.toBeInTheDocument();
  });

  it("shows the last kept run when a skill's run panel opens", async () => {
    const { client } = setup();
    client.skillRows = [{ id: "s1", title: "Check a supplier", description: "Looks a supplier up.", kind: "procedure", instructions: "Search.", module: null, action: null, inputs: [], produces: "", sources: [], created_by: "person", state: "active", created_at: "2026-09-28T10:00:00Z", updated_at: "2026-09-28T10:00:00Z" }];
    client.skillRuns = [{ run_id: "r1", skill_id: "s1", inputs: { supplier: "Acme" }, state: "done", summary: "Acme still ships.", items: [{ name: "Acme", source: "not a url" }], evidence: [], started_at: "2026-09-28T09:00:00Z", finished_at: "2026-09-28T09:00:30Z" }];
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Skills" }));
    const card = await screen.findByRole("article", { name: "Check a supplier" });
    await user.click(within(card).getByRole("button", { name: "Run" }));
    expect(await within(card).findByText("Acme still ships.")).toBeInTheDocument();
    expect(within(card).getByText(/Last time \(.*Acme\)/)).toBeInTheDocument();
    expect(within(card).getByText("not a url")).toBeInTheDocument();
  });

  it("makes a skill, runs it with its inputs and shows what it found", async () => {
    const { client } = setup();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Skills" }));
    expect(await screen.findByText(/No skills yet/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New skill" }));
    await user.type(screen.getByLabelText("Name"), "Find people to cold call");
    await user.type(screen.getByLabelText("What it does"), "Finds people worth calling.");
    await user.type(screen.getByLabelText(/How Alpha does it/), "Search, read, list.");
    await user.type(screen.getByLabelText(/It needs/), "industry, city?");
    await user.type(screen.getByLabelText("Sources it may read"), "LinkedIn");
    await user.click(screen.getByRole("button", { name: "Save skill" }));
    await waitFor(() => expect(client.skillCalls).toEqual(["create find_people_to_cold_call"]));
    const created = client.skillRows[0];
    expect(created.inputs).toEqual([
      { name: "industry", description: "", required: true },
      { name: "city", description: "", required: false },
    ]);
    const card = await screen.findByRole("article", { name: "Find people to cold call" });
    expect(within(card).getByText("Needs: industry, city (optional)")).toBeInTheDocument();
    expect(within(card).getByText("Reads: LinkedIn")).toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: "Run" }));
    await user.type(within(card).getByLabelText("Industry"), "logistics");
    await user.click(within(card).getByRole("button", { name: "Run now" }));
    await waitFor(() => expect(client.skillCalls).toContain('run find_people_to_cold_call {"industry":"logistics"}'));
    expect(await within(card).findByText("Found two people worth a call.")).toBeInTheDocument();
    const table = within(card).getByRole("table", { name: "What it found" });
    expect(within(table).getByText("Ada Example")).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "example.com" })).toHaveAttribute("href", "https://example.com/ada");
    expect(within(table).getByText("https://example.com/ben (via https://example.com/roundup)")).toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: "Retire Find people to cold call" }));
    await waitFor(() => expect(screen.queryByRole("article", { name: "Find people to cold call" })).not.toBeInTheDocument());
  });

  it("lists every automation and module connection across modules, switchable in place", async () => {
    const { client } = setup();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Automations" }));
    const auto = await screen.findByRole("table", { name: "Automations" });
    expect(within(auto).getByText("Look for new roles")).toBeInTheDocument();
    expect(within(auto).getByText("every day at 09:00")).toBeInTheDocument();
    await user.click(within(auto).getByLabelText("Look for new roles on"));
    await waitFor(() => expect(client.scheduleRows.jobs[0].enabled).toBe(false));

    await user.click(screen.getByRole("tab", { name: "Connections" }));
    // Accounts and services (formerly under Settings) now live on this tab too.
    expect(await screen.findByRole("heading", { name: "Connections" })).toBeInTheDocument();
    expect(screen.getByText(/Accounts and services your modules may use/)).toBeInTheDocument();
    const links = await screen.findByRole("table", { name: "Module connections" });
    expect(within(links).getAllByText(/to list your courses/).length).toBeGreaterThan(0);
    await user.click(within(links).getAllByLabelText("Job profile reads Academics")[0]);
    await waitFor(() => expect(client.connectionRows[0].enabled).toBe(false));
  });
});
