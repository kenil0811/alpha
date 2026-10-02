import { ToastProvider } from "../ui/toast";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { FakeWorkflowsClient } from "../test/fakeWorkflows";
import { Settings } from "./Info";

const health = { status: "ok", core_version: "t", contract_version: "0.2", core_instance_id: "t", python_version: "3", python_executable: "p", data_dir: "/data", worker_profiles: [], active_runs: [] };

describe("modules removed earlier", () => {
  it("are named in Settings and deleted for good only after a second yes", async () => {
    const client = new FakeWorkflowsClient();
    client.leftovers = [
      { app_id: "jobs", name: "Job Search Watcher" },
      { app_id: "books", name: "Reading list" },
    ];
    const user = userEvent.setup();
    render(<ToastProvider><Settings client={client} health={health} theme="dark" onTheme={() => undefined} section="data" /></ToastProvider>);
    const block = await screen.findByLabelText("Removed projects");
    expect(block).toHaveTextContent("Job Search Watcher, Reading list");
    expect(block).toHaveTextContent("Deleting cannot be undone");
    await user.click(screen.getByRole("button", { name: "Delete 2" }));
    expect(client.leftovers).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "Delete for good" }));
    expect(await screen.findByText("Deleted 2 projects and everything about them.")).toBeInTheDocument();
    expect(client.leftovers).toEqual([]);
  });

  it("says nothing when there are none", async () => {
    render(<ToastProvider><Settings client={new FakeWorkflowsClient()} health={health} theme="dark" onTheme={() => undefined} section="data" /></ToastProvider>);
    await screen.findByRole("heading", { name: "Settings" });
    expect(screen.queryByLabelText("Removed projects")).not.toBeInTheDocument();
  });
});
