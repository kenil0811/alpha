import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { FakeCoreClient } from "../test/fakeClient";

beforeEach(() => window.localStorage.clear());

describe("a one-click yes", () => {
  it("sends the person's yes as their own message and stands only on the newest reply", async () => {
    const client = new FakeCoreClient();
    const said: string[] = [];
    client.sessionScript = (session, text) => {
      said.push(text);
      const agreed = text.startsWith("Yes, allow");
      return {
        turn_id: `a_${said.length}`,
        sequence: session.turn_count + 1,
        role: "alpha",
        kind: agreed ? "work" : "text",
        text: agreed ? "Connections list may now read linkedin.com through your sign-in." : "You are signed in to LinkedIn; this module just hasn't been allowed to use that sign-in. Allow it?",
        detail: agreed ? { kind: "allow" } : { kind: "answer", offer: { kind: "allow_site", label: "Allow linkedin.com and try again", say: "Yes, allow Connections list to read linkedin.com through my sign-in, then try again." } },
        created_at: new Date().toISOString(),
      };
    };
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByText("Runtime connected");
    await user.type(screen.getByLabelText("Message"), "why is the sync not working");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await user.click(await screen.findByRole("button", { name: "Allow linkedin.com and try again" }));
    await waitFor(() => expect(said).toEqual(["why is the sync not working", "Yes, allow Connections list to read linkedin.com through my sign-in, then try again."]));
    expect(await screen.findByText(/may now read linkedin.com through your sign-in/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Allow linkedin.com and try again" })).not.toBeInTheDocument();
  });
});
