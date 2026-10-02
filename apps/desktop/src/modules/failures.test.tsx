import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FakeWorkflowsClient, sampleDetail } from "../test/fakeWorkflows";
import { ModulePage } from "./ModulePage";

describe("what went wrong", () => {
  it("names each failure in plain words with what Alpha did about it", async () => {
    const fake = new FakeWorkflowsClient();
    fake.details.set("notes-list-1a2b3c", sampleDetail());
    fake.failures = [
      {
        run_id: "run_1",
        app_id: "notes-list-1a2b3c",
        action_id: "search",
        at: "2026-09-29T12:01:19Z",
        kind: "module_code",
        where: "handlers.py line 551",
        said: "Search new listings stopped in the project's own code (handlers.py line 551): TypeError: estimated values must map a field.",
        repair: { repair_id: "repair_1", state: "fixed", summary: "Alpha fixed it (passed the model result as the estimate source) and ran Search new listings again: Added 12 new listing(s)." },
      },
      {
        run_id: "run_2",
        app_id: "notes-list-1a2b3c",
        action_id: "sync",
        at: "2026-09-27T20:09:54Z",
        kind: "platform",
        where: null,
        said: "Sync hit a problem inside Alpha itself (TypeError): Web.get() got an unexpected keyword argument 'rendered'. This is not the project's fault.",
        repair: null,
      },
    ];
    render(<ModulePage client={fake} appId="notes-list-1a2b3c" onAsk={() => undefined} onCancelRun={async () => undefined} />);
    await screen.findByRole("heading", { name: "Notes list" });
    const block = await screen.findByLabelText("What went wrong");
    expect(within(block).getByText("Fixed")).toBeInTheDocument();
    expect(block).toHaveTextContent("stopped in the project's own code (handlers.py line 551)");
    expect(block).toHaveTextContent("ran Search new listings again: Added 12 new listing(s)");
    expect(within(block).getByText("Alpha's own problem")).toBeInTheDocument();
    expect(block).toHaveTextContent("This is not the project's fault");
    expect(block.textContent).not.toMatch(/Something went wrong/);
  });
});
