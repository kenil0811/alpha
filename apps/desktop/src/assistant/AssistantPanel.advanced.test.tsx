import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { FakeCoreClient } from "../test/fakeClient";

beforeEach(() => {
  localStorage.clear();
});

describe("the composer's Advanced choice reaches the send payload", () => {
  it("a non-default access mode is carried on sendSession's options", async () => {
    const client = new FakeCoreClient();
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByRole("status");

    await user.click(screen.getByRole("button", { name: "Add files, folders, images or audio" }));
    const advancedItem = await screen.findByRole("menuitem", { name: /Advanced/ });
    advancedItem.focus();
    await user.keyboard("{ArrowRight}");
    (await screen.findByRole("menuitem", { name: /Approve for me/ })).focus();
    await user.keyboard("{Enter}");

    await user.type(screen.getByLabelText("Message"), "log two eggs");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(client.sendOptions.at(-1)).toMatchObject({ accessMode: "approve_for_me" });
  });
});
