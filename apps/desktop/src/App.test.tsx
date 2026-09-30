import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { App } from "./App";
import { FakeCoreClient } from "./test/fakeClient";

beforeEach(() => {
  window.localStorage.clear();
});
afterEach(() => {
  window.location.hash = "";
});

describe("connections moved to Intelligence", () => {
  it.each(["#/connections", "#/settings/connections"])("redirects %s to Intelligence's Connections tab", async (hash) => {
    window.location.hash = hash;
    render(<App client={new FakeCoreClient()} />);
    expect(await screen.findByRole("tab", { name: "Connections", selected: true })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Connections/ })).toBeInTheDocument();
    // The old Settings section is gone; Connections lives only on Intelligence now.
    await userEvent.setup().click(screen.getByRole("button", { name: "Settings" }));
    expect(screen.queryByRole("button", { name: "Connections" })).not.toBeInTheDocument();
  });
});

describe("the shell frame", () => {
  it("opens on Home with the assistant beside it, and Activity starts empty", async () => {
    const user = userEvent.setup();
    render(<App client={new FakeCoreClient()} />);
    expect(await screen.findByText("Runtime connected")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Good (morning|afternoon|evening)/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Message")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Activity" }));
    expect(screen.getByText(/Nothing has run yet/)).toBeInTheDocument();
    // The assistant stays beside every surface.
    expect(screen.getByLabelText("Message")).toBeInTheDocument();
  });

  it("shows a failed run in Activity with a plain-language reason", async () => {
    const client = new FakeCoreClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByText("Runtime connected");
    await user.click(screen.getByRole("button", { name: "Activity" }));
    await act(async () => {
      await client.createRun({ text: "x" });
      client.start("run_1");
      client.fail("run_1", "worker_error");
    });
    const list = await screen.findByRole("list", { name: "Runs" });
    await waitFor(() => expect(within(list).getByText("Failed")).toBeInTheDocument());
    expect(within(list).getByText(/the worker reported an error/)).toBeInTheDocument();
  });

  it("cancels a running run from Activity", async () => {
    const client = new FakeCoreClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByText("Runtime connected");
    await user.click(screen.getByRole("button", { name: "Activity" }));
    await act(async () => {
      await client.createRun({ text: "hang" });
      client.start("run_1");
    });
    const list = await screen.findByRole("list", { name: "Runs" });
    await waitFor(() => expect(within(list).getByText("Running")).toBeInTheDocument());
    await user.click(within(list).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(within(list).getByText("Cancelled")).toBeInTheDocument());
    expect(client.runs.get("run_1")?.state).toBe("cancelled");
  });

  it("explains when no runtime session is available", async () => {
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("No runtime session");
    expect(screen.getByRole("status")).toHaveTextContent("Runtime unavailable");
  });
});
