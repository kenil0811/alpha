/** The newest "not connected" turn opens the browser sign-in by itself: Claude then takes the
 *  code its page shows (Bridge's flow), ChatGPT's CLI finishes on its own and is polled. Either
 *  way the message is resent once connected; an older card in the history never opens it. */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FakeWorkflowsClient } from "../test/fakeWorkflows";
import { NotConnectedCard, shortReason } from "./NotConnectedCard";

function signedOutClient() {
  const client = new FakeWorkflowsClient();
  client.providers = client.providers.map((p) => (p.id === "claude" ? { ...p, state: "needs_sign_in", signed_in: false } : p));
  return client;
}

describe("NotConnectedCard", () => {
  it("opens Claude's sign-in straight away, takes the pasted code and resends", async () => {
    const client = signedOutClient();
    const onResend = vi.fn();
    const user = userEvent.setup();
    render(<NotConnectedCard info={{ kind: "sign_in", provider: "claude" }} client={client} onResend={onResend} auto />);
    await waitFor(() => expect(client.signInCalls).toEqual(["claude"]));
    await user.type(await screen.findByLabelText("Claude sign-in code"), "abc#state");
    await user.click(screen.getByRole("button", { name: "Connect" }));
    await waitFor(() => expect(onResend).toHaveBeenCalledTimes(1));
    expect(client.finishCodes).toEqual(["abc#state"]);
  });

  it("polls ChatGPT's own sign-in and resends once it lands", async () => {
    const client = new FakeWorkflowsClient();
    const onResend = vi.fn();
    render(<NotConnectedCard info={{ kind: "sign_in", provider: "chatgpt" }} client={client} onResend={onResend} auto />);
    await waitFor(() => expect(client.signInCalls).toEqual(["chatgpt"]));
    expect(await screen.findByText(/Finish signing in in your browser/)).toBeInTheDocument();
    client.providers = client.providers.map((p) => (p.id === "chatgpt" ? { ...p, state: "connected", signed_in: true } : p));
    await waitFor(() => expect(onResend).toHaveBeenCalledTimes(1), { timeout: 5000 });
  });

  it("without Codex shows Install Codex, then Connect, never a terminal", async () => {
    const client = new FakeWorkflowsClient();
    client.providers = client.providers.map((p) => (p.id === "chatgpt" ? { ...p, state: "cli_missing", cli_present: false } : p));
    const user = userEvent.setup();
    render(<NotConnectedCard info={{ kind: "sign_in", provider: "chatgpt" }} client={client} onResend={() => undefined} auto />);
    await user.click(await screen.findByRole("button", { name: "Install Codex" }));
    expect(client.installCalls).toEqual(["chatgpt"]);
    expect(client.signInCalls).toEqual([]);
    await user.click(await screen.findByRole("button", { name: "Connect ChatGPT" }));
    expect(client.signInCalls).toEqual(["chatgpt"]);
  });

  it("an older card waits for a click", async () => {
    const client = signedOutClient();
    render(<NotConnectedCard info={{ kind: "sign_in", provider: "claude" }} client={client} onResend={() => undefined} />);
    expect(screen.getByRole("button", { name: "Sign in to Claude" })).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 50));
    expect(client.signInCalls).toEqual([]);
  });
});

describe("a failed reply says why", () => {
  it("shows Core's short reason on one line, with Try again", () => {
    render(<NotConnectedCard info={{ kind: "generic", provider: "chatgpt" }} client={{}} onResend={() => undefined} reason="I can't reach the model: it took too long to respond. Try again." />);
    expect(screen.getByText("ChatGPT couldn't answer.")).toBeInTheDocument();
    expect(screen.getByText("It took too long to respond. Try again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("drops a reason that only says to try again", () => {
    expect(shortReason("I can't reach the model right now. Try again in a moment.")).toBeNull();
    expect(shortReason("I can't reach that model right now (no route). Pick one.")).toBe("No route. Pick one.");
  });
});
