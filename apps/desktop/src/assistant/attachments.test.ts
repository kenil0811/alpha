import { describe, expect, it, vi } from "vitest";
import { attachmentFromPath, kindOfName, registerAttachmentHandler, toWire, unclaimed } from "./attachments";

describe("kindOfName", () => {
  it("classes images and audio by extension or mime, everything else as a plain file", () => {
    expect(kindOfName("photo.png")).toBe("image");
    expect(kindOfName("clip.m4a")).toBe("audio");
    expect(kindOfName("weird", "image/webp")).toBe("image");
    expect(kindOfName("notes.txt")).toBe("file");
  });
});

describe("attachmentFromPath", () => {
  it("takes the name from the end of a desktop path", () => {
    const a = attachmentFromPath("/Users/me/Documents/report.pdf");
    expect(a.name).toBe("report.pdf");
    expect(a.path).toBe("/Users/me/Documents/report.pdf");
    expect(a.kind).toBe("file");
  });

  it("respects a kind hint (a folder, or an audio pick from its own filter)", () => {
    expect(attachmentFromPath("/x/proj", "folder").kind).toBe("folder");
    expect(attachmentFromPath("/x/memo.raw", "audio").kind).toBe("audio");
  });
});

describe("toWire", () => {
  it("carries a desktop path and never invents a content field", () => {
    const wire = toWire(attachmentFromPath("/a/b/c.txt"));
    expect(wire).toEqual({ kind: "file", name: "c.txt", size: null, mime: null, path: "/a/b/c.txt", content_b64: null });
  });
});

describe("unclaimed", () => {
  it("caps what a message may carry to the room left", () => {
    const files = Array.from({ length: 5 }, (_, i) => attachmentFromPath(`/f${i}.txt`));
    expect(unclaimed(files, 8)).toHaveLength(2); // MAX_ATTACHMENTS is 10
  });

  it("lets a registered handler claim a file before it becomes a plain attachment", () => {
    const handled = vi.fn();
    const unregister = registerAttachmentHandler((f) => f.name.endsWith(".alphamodule"), handled);
    const module = attachmentFromPath("/x/export.alphamodule");
    const plain = attachmentFromPath("/x/notes.txt");
    const rest = unclaimed([module, plain], 0);
    expect(handled).toHaveBeenCalledWith(module);
    expect(rest).toEqual([plain]);
    unregister();
  });

  it("unregistering stops a handler from claiming further files", () => {
    const handled = vi.fn();
    const unregister = registerAttachmentHandler((f) => f.name.endsWith(".special"), handled);
    unregister();
    const file = attachmentFromPath("/x/thing.special");
    const rest = unclaimed([file], 0);
    expect(handled).not.toHaveBeenCalled();
    expect(rest).toEqual([file]);
  });
});
