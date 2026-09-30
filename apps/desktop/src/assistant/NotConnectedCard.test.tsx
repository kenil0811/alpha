/** A model-call failure (Core's `model_error` on the turn) shows a guided "not connected" card
 *  instead of plain text, and clears once the person gets connected - resending what they asked. */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { FakeCoreClient } from "../test/fakeClient";

beforeEach(() => window.localStorage.clear());

describe("not connected to a model", () => {
  it("shows a guided sign-in card, then resends automatically once signed in", async () => {
    const client = new FakeCoreClient();
    let attempts = 0;
    client.providers = client.providers.map((p) => (p.id === "claude" ? { ...p, state: "cli_missing", cli_present: false } : p));
    client.sessionScript = (session, text) => {
      attempts += 1;
      const stillFailing = attempts === 1;
      return {
        turn_id: `a_${attempts}`,
        sequence: session.turn_count + 1,
        role: "alpha",
        kind: "text",
        text: stillFailing ? "I can't reach the model: the `claude` command isn't installed." : `Got it: ${text}`,
        detail: stillFailing ? { model_error: { kind: "sign_in", provider: "claude" } } : undefined,
        created_at: new Date().toISOString(),
      };
    };
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByText("Runtime connected");
    await user.type(screen.getByLabelText("Message"), "log two eggs");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Not connected to Claude.")).toBeInTheDocument();
    client.providers = client.providers.map((p) => (p.id === "claude" ? { ...p, state: "connected", signed_in: true } : p));
    await user.click(screen.getByRole("button", { name: "I've signed in" }));

    await waitFor(() => expect(attempts).toBe(2));
    expect(await screen.findByText("Got it: log two eggs")).toBeInTheDocument();
  });

  it("saves a key inline for a key-based provider and resends", async () => {
    const client = new FakeCoreClient();
    let attempts = 0;
    client.sessionScript = (session, text) => {
      attempts += 1;
      const stillFailing = attempts === 1;
      return {
        turn_id: `a_${attempts}`,
        sequence: session.turn_count + 1,
        role: "alpha",
        kind: "text",
        text: stillFailing ? "I can't reach the model: no key is saved for it yet." : `Got it: ${text}`,
        detail: stillFailing ? { model_error: { kind: "key", provider: "grok" } } : undefined,
        created_at: new Date().toISOString(),
      };
    };
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByText("Runtime connected");
    await user.type(screen.getByLabelText("Message"), "what's the weather");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Not connected to Grok.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Grok key"), "xai-test-key");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(client.providers.find((p) => p.id === "grok")?.state).toBe("key_saved"));
    expect(await screen.findByText("Got it: what's the weather")).toBeInTheDocument();
  });
});
