import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { App } from "./App";
import { FakeCoreClient } from "./test/fakeClient";

async function openRuntimeFixture(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole("status");
  await user.click(screen.getByRole("button", { name: "Runtime fixture" }));
}

describe("shell request/result path", () => {
  it("shows the connected runtime and an empty result state", async () => {
    render(<App client={new FakeCoreClient()} />);
    expect(await screen.findByRole("status")).toHaveTextContent("Runtime connected");
    expect(screen.getByText(/Nothing has run yet/)).toBeInTheDocument();
    expect(screen.getByLabelText("What do you want done?")).toBeInTheDocument();
  });

  it("submits text, follows live status and shows the worker output", async () => {
    const client = new FakeCoreClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    await openRuntimeFixture(user);
    await user.type(screen.getByLabelText("Text to send"), "hello alpha");
    await user.click(screen.getByRole("button", { name: "Run" }));

    const list = await screen.findByRole("list", { name: "Runs" });
    expect(within(list).getByText("Queued")).toBeInTheDocument();
    expect(screen.getByLabelText("Text to send")).toHaveValue("");
    await waitFor(() => expect(screen.getByLabelText("Text to send")).toHaveFocus());

    await act(async () => {
      client.start("run_1");
      client.progress("run_1", 1);
      client.succeed("run_1", { upper: "HELLO ALPHA", words: 2, characters: 11 });
    });
    await waitFor(() => expect(within(list).getByText("Done")).toBeInTheDocument());
    expect(within(list).getByText(/HELLO ALPHA/)).toBeInTheDocument();
    expect(within(list).getByText(/2 words · 11 characters/)).toBeInTheDocument();
    expect(within(list).getByText(/4 events · 1 progress updates/)).toBeInTheDocument();
    expect(within(list).queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("keeps every event when Core emits before the create response returns", async () => {
    const client = new FakeCoreClient();
    client.beforeCreateResolves = (runId) => {
      client.start(runId);
      client.progress(runId, 1);
      client.progress(runId, 2);
    };
    const user = userEvent.setup();
    render(<App client={client} />);
    await openRuntimeFixture(user);
    await user.type(screen.getByLabelText("Text to send"), "fast");
    await user.click(screen.getByRole("button", { name: "Run" }));
    const list = await screen.findByRole("list", { name: "Runs" });
    await act(async () => {
      client.progress("run_1", 3);
      client.succeed("run_1", { upper: "FAST", words: 1, characters: 4 });
    });
    await waitFor(() => expect(within(list).getByText("Done")).toBeInTheDocument());
    // queued, started, 3 progress, succeeded
    expect(within(list).getByText(/6 events · 3 progress updates/)).toBeInTheDocument();
  });

  it("displays a failed run with a plain-language reason", async () => {
    const client = new FakeCoreClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    await openRuntimeFixture(user);
    await user.type(screen.getByLabelText("Text to send"), "x");
    await user.selectOptions(screen.getByLabelText("Worker behavior"), "fail");
    await user.click(screen.getByRole("button", { name: "Run" }));
    await act(async () => {
      client.start("run_1");
      client.fail("run_1", "worker_error");
    });
    const list = await screen.findByRole("list", { name: "Runs" });
    await waitFor(() => expect(within(list).getByText("Failed")).toBeInTheDocument());
    expect(within(list).getByText(/the worker reported an error/)).toBeInTheDocument();
  });

  it("cancels a running run from the result card", async () => {
    const client = new FakeCoreClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    await openRuntimeFixture(user);
    await user.type(screen.getByLabelText("Text to send"), "hang");
    await user.click(screen.getByRole("button", { name: "Run" }));
    await act(async () => {
      client.start("run_1");
    });
    const list = await screen.findByRole("list", { name: "Runs" });
    await waitFor(() => expect(within(list).getByText("Running")).toBeInTheDocument());
    await user.click(within(list).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(within(list).getByText("Cancelled")).toBeInTheDocument());
    expect(within(list).getByText(/you cancelled it/)).toBeInTheDocument();
    expect(client.runs.get("run_1")?.state).toBe("cancelled");
  });

  it("reports a start failure instead of pretending a run exists", async () => {
    const client = new FakeCoreClient();
    client.failCreate = true;
    const user = userEvent.setup();
    render(<App client={client} />);
    await openRuntimeFixture(user);
    await user.type(screen.getByLabelText("Text to send"), "x");
    await user.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not start");
    expect(screen.getByText(/Nothing has run yet/)).toBeInTheDocument();
  });

  it("explains when no runtime session is available", async () => {
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("No runtime session");
    expect(screen.getByRole("status")).toHaveTextContent("Runtime unavailable");
  });
});
