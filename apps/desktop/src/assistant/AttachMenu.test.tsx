import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AttachMenu, AttachmentChips, useAttachments } from "./AttachMenu";
import { attachmentFromPath, pickFilesOrImages } from "./attachments";

vi.mock("./attachments", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./attachments")>();
  return { ...actual, pickFilesOrImages: vi.fn() };
});

function Harness() {
  const attach = useAttachments();
  return (
    <div>
      <AttachMenu onAdd={attach.add} />
      <AttachmentChips items={attach.items} onRemove={attach.remove} />
    </div>
  );
}

describe("attachment chips", () => {
  it("shows a chip for each attachment, with its name and size", () => {
    function Filled() {
      return <AttachmentChips items={[{ id: "1", kind: "file", name: "notes.txt", size: 2048 }]} onRemove={() => undefined} />;
    }
    render(<Filled />);
    expect(screen.getByText("notes.txt")).toBeInTheDocument();
    expect(screen.getByText("2 KB")).toBeInTheDocument();
  });

  it("removing a chip calls onRemove with its id, and nothing when there are none", () => {
    const onRemove = vi.fn();
    const { rerender } = render(<AttachmentChips items={[{ id: "a1", kind: "image", name: "x.png" }]} onRemove={onRemove} />);
    screen.getByRole("button", { name: "Remove x.png" }).click();
    expect(onRemove).toHaveBeenCalledWith("a1");
    rerender(<AttachmentChips items={[]} onRemove={onRemove} />);
    expect(screen.queryByLabelText("Attached")).not.toBeInTheDocument();
  });
});

describe("the + menu picks files and queues them", () => {
  it("adding files from the menu renders a chip, and removing it clears the queue", async () => {
    vi.mocked(pickFilesOrImages).mockResolvedValue([attachmentFromPath("/tmp/report.pdf")]);
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Add files, folders, images or audio" }));
    await user.click(await screen.findByRole("menuitem", { name: /Add files or images/ }));
    expect(await screen.findByText("report.pdf")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove report.pdf" }));
    expect(screen.queryByText("report.pdf")).not.toBeInTheDocument();
  });
});
