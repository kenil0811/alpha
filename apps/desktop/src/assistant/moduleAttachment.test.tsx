/** An exported module (`.alphamodule`) attached in any composer installs as a module instead of
 *  riding along as message context (App.tsx's `registerAttachmentHandler` call). Covers both
 *  shapes a `PendingAttachment` can carry: a desktop path, and web/drop/paste bytes. */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { FakeWorkflowsClient, sampleDetail } from "../test/fakeWorkflows";
import { attachmentFromPath, unclaimed, type PendingAttachment } from "./attachments";

beforeEach(() => {
  window.localStorage.clear();
});

describe("attaching an exported module", () => {
  it("a path attachment installs by path, opens the module, and never becomes a chip", async () => {
    const client = new FakeWorkflowsClient();
    client.importResult = { app_id: "imported-1", name: "Imported module" };
    client.details.set("imported-1", sampleDetail({ app_id: "imported-1", name: "Imported module" }));
    render(<App client={client} />);
    await screen.findByText("Runtime connected");

    const attachment = attachmentFromPath("/Users/me/Downloads/x.alphamodule");
    const rest = unclaimed([attachment], 0);

    expect(rest).toEqual([]); // claimed, not left to become a composer chip
    await waitFor(() => expect(client.importedFiles).toEqual([{ path: "/Users/me/Downloads/x.alphamodule" }]));
    expect(await screen.findByRole("heading", { name: "Imported module" })).toBeInTheDocument();
  });

  it("a contentB64 attachment installs as a Blob", async () => {
    const client = new FakeWorkflowsClient();
    client.importResult = { app_id: "imported-2", name: "Imported from bytes" };
    client.details.set("imported-2", sampleDetail({ app_id: "imported-2", name: "Imported from bytes" }));
    render(<App client={client} />);
    await screen.findByText("Runtime connected");

    const attachment: PendingAttachment = { id: "att_1", kind: "file", name: "x.alphamodule", contentB64: btoa("zip-bytes") };
    const rest = unclaimed([attachment], 0);

    expect(rest).toEqual([]);
    await waitFor(() => expect(client.importedFiles).toHaveLength(1));
    expect(client.importedFiles[0]).toBeInstanceOf(Blob);
    expect(await screen.findByRole("heading", { name: "Imported from bytes" })).toBeInTheDocument();
  });
});
