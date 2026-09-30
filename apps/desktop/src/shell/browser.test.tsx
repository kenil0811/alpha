/** The signed-in browser in the shell: connecting a site on Intelligence's Connections tab, and
 *  switching it on for one module in that module's Settings. */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { App } from "../App";
import { ModulePage } from "../modules/ModulePage";
import { FakeWorkflowsClient, sampleDetail } from "../test/fakeWorkflows";

describe("the signed-in browser", () => {
  it("lets the person sign in to a site from Connections and shows where it stands", async () => {
    const client = new FakeWorkflowsClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    expect(await screen.findByText("Runtime connected")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Intelligence" }));
    await user.click(screen.getByRole("tab", { name: "Connections" }));
    const form = await screen.findByRole("form", { name: "Sign in to a site" });
    await user.type(within(form).getByLabelText("Sign in to a site"), "https://www.LinkedIn.com/login");
    await user.click(within(form).getByRole("button", { name: "Sign in…" }));
    expect(await screen.findByText(/A browser window has opened/)).toBeInTheDocument();
    const list = screen.getByLabelText("Signed-in sites");
    expect(within(list).getByText("linkedin.com")).toBeInTheDocument();
    expect(within(list).getByText(/Waiting for you to sign in/)).toBeInTheDocument();
    await user.click(within(list).getByRole("button", { name: "Remove linkedin.com" }));
    await waitFor(() => expect(within(list).queryByText("linkedin.com")).not.toBeInTheDocument());
  });

  it("is off per module until switched on in the module's Settings", async () => {
    const client = new FakeWorkflowsClient();
    client.sites = [{ site: "linkedin.com", state: "connected", connected_at: "2026-09-27T18:00:00Z", last_error: null, apps: [] }];
    client.details.set("notes-list-1a2b3c", sampleDetail({ capabilities: ["records", "http", "browser"] }));
    const user = userEvent.setup();
    render(<ModulePage client={client} appId="notes-list-1a2b3c" onAsk={() => undefined} />);
    await screen.findByRole("heading", { name: "Notes list" });
    const access = await screen.findByLabelText("Signed-in browser access");
    expect(within(access).getByText(/Off: this module reads it as a visitor/)).toBeInTheDocument();
    await user.click(within(access).getByLabelText("Allow linkedin.com"));
    await waitFor(() => expect(client.access.get("notes-list-1a2b3c")).toEqual(["linkedin.com"]));
    expect(await within(access).findByText(/may read through your session/)).toBeInTheDocument();
  });
});
