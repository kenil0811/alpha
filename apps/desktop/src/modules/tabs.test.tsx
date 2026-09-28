import { describe, expect, it } from "vitest";
import type { AppDetail } from "../core/client";
import { sampleDetail } from "../test/fakeWorkflows";
import { moduleTabs } from "./ModulePage";

describe("a module's tabs", () => {
  it("gives every table a page, after the summary and any declared screen tabs", () => {
    const detail = sampleDetail({
      summary: [{ kind: "metrics", cards: [{ title: "Notes", view: "notes.by_day", metric: "count" }] }],
      collections: [
        { name: "notes", fields: [{ name: "title", kind: "text" }] },
        { name: "tags", fields: [{ name: "name", kind: "text" }] },
      ],
    });
    expect(moduleTabs(detail).map((t) => t.title)).toEqual(["Summary", "Notes", "Tags", "Actions"]);
  });

  it("lets a declared screen tab that already lists a table stand in for its page", () => {
    const detail = sampleDetail({
      views: [{ id: "notes.recent", kind: "records", collection: "notes", where: null, fields: null, filterable: [], sortable: [], default_order: [], max_limit: 50, group_by: [], metrics: [] }],
      screen: { tabs: [{ id: "today", title: "Today", blocks: [{ kind: "table", view: "notes.recent", columns: [{ field: "title" }] }] }] } as unknown as AppDetail["screen"],
      collections: [
        { name: "notes", fields: [{ name: "title", kind: "text" }] },
        { name: "tags", fields: [{ name: "name", kind: "text" }] },
      ],
    });
    expect(moduleTabs(detail).map((t) => t.title)).toEqual(["Today", "Tags"]);
  });
});
