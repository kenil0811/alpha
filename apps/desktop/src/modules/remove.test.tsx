import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { FakeWorkflowsClient, sampleDetail } from "../test/fakeWorkflows";
import { ModulePage } from "./ModulePage";

describe("removing a module", () => {
  it("asks once, then takes the module out of use and leaves the page", async () => {
    const fake = new FakeWorkflowsClient();
    fake.details.set("notes-list-1a2b3c", sampleDetail());
    let left = 0;
    const user = userEvent.setup();
    render(<ModulePage client={fake} appId="notes-list-1a2b3c" onAsk={() => undefined} onRemoved={() => void (left += 1)} />);
    await screen.findByRole("heading", { name: "Notes list" });
    await user.click(screen.getByRole("tab", { name: "Settings" }));
    await user.click(await screen.findByRole("button", { name: "Remove this module" }));
    expect(screen.getByText("Remove Notes list and all its data?")).toBeInTheDocument();
    expect(screen.getByText(/everything that exists because of it/)).toBeInTheDocument();
    expect(fake.removed).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Remove" }));
    expect(fake.removed).toEqual(["notes-list-1a2b3c"]);
    expect(left).toBe(1);
  });
});
