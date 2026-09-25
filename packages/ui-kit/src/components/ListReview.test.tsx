import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { AlphaProvider, useAction, useView, type RecordRow } from "../data/hooks";
import { allOf, contains, eq, orderBy } from "../data/query";
import { createMemoryApp, type MemoryApp } from "../testing/memoryApp";
import { Button, NumberField, TextField, parseNumber } from "./controls";
import { DetailDrawer } from "./DetailDrawer";
import { OperationStatus, ProvenanceNote } from "./feedback";
import { FilterBar, type FilterValues } from "./FilterBar";
import { Form } from "./Form";
import { RecordTable, Pager, type SortState } from "./RecordTable";
import { ReviewQueue } from "./ReviewQueue";

type Entry = { title: string; amount?: number; kind: string; status?: string };

const KINDS = [
  { value: "note", label: "Note" },
  { value: "task", label: "Task" },
];

function Editor({ row, onDone }: { row: RecordRow<Entry>; onDone: () => void }) {
  const save = useAction("update_entry");
  const [title, setTitle] = useState(row.values.title);
  const [amount, setAmount] = useState(row.values.amount === undefined ? "" : String(row.values.amount));
  const parsed = parseNumber(amount);
  return (
    <Form
      onSubmit={async () => {
        if (!parsed.ok) return;
        try {
          await save.run({ id: row.id, expected_revision: row.revision, changes: { title, amount: parsed.value } });
          onDone();
        } catch {
          /* shown by OperationStatus; the draft stays */
        }
      }}
    >
      <TextField label="Title" value={title} onChange={(e) => setTitle(e.target.value)} required />
      <NumberField label="Amount" value={amount} onValueChange={setAmount} error={parsed.ok ? null : parsed.message} />
      <ProvenanceNote provenance={row.provenance.amount} />
      <Button type="submit" variant="primary" busy={save.state === "saving"} busyLabel="Saving…">
        Save changes
      </Button>
      <OperationStatus state={save.state} error={save.error} />
    </Form>
  );
}

function ListScreen() {
  const [filters, setFilters] = useState<FilterValues>({ search: "", kind: "" });
  const [sort, setSort] = useState<SortState>({ field: "title", direction: "asc" });
  const [open, setOpen] = useState<RecordRow<Entry> | null>(null);
  const view = useView<Entry>("entries.list", {
    where: allOf(filters.search ? contains("title", filters.search) : undefined, filters.kind ? eq("kind", filters.kind) : undefined),
    order_by: orderBy(sort.direction === "desc" ? `-${sort.field}` : sort.field),
    limit: 3,
  });
  return (
    <>
      <FilterBar
        searchLabel="Search titles"
        filters={[{ id: "kind", label: "Kind", options: KINDS }]}
        values={filters}
        onChange={setFilters}
        debounceMs={0}
        resultLabel={view.loading ? "Loading…" : `${view.records.length} shown`}
      />
      <RecordTable<RecordRow<Entry>>
        caption="Entries"
        columns={[
          { id: "title", header: "Title", cell: (r) => r.values.title, sortField: "title" },
          { id: "amount", header: "Amount", cell: (r) => r.values.amount ?? "—", numeric: true, sortField: "amount" },
          { id: "kind", header: "Kind", cell: (r) => r.values.kind },
        ]}
        rows={view.records}
        getRowId={(r) => r.id}
        getRowLabel={(r) => r.values.title}
        onOpen={setOpen}
        sort={sort}
        onSortChange={setSort}
        loading={view.loading}
        error={view.error}
        empty={{ title: "No entries match", message: "Clear the filters to see everything." }}
        footer={<Pager label={`Page ${view.page + 1}`} hasPrevious={view.hasPrevious} hasNext={view.hasNext} onPrevious={view.previous} onNext={view.next} />}
      />
      <DetailDrawer open={open !== null} onClose={() => setOpen(null)} title={open?.values.title ?? ""}>
        {open ? <Editor row={open} onDone={() => setOpen(null)} /> : null}
      </DetailDrawer>
    </>
  );
}

async function app(): Promise<MemoryApp> {
  return createMemoryApp({
    collections: {
      entries: [
        { title: "Alpha paper", amount: 3, kind: "note", status: "new" },
        { title: "Blue pens", amount: 7, kind: "task", status: "new" },
        { title: "Coffee filters", amount: 1, kind: "task", status: "kept" },
        { title: "Desk lamp", kind: "note", status: "new" },
      ],
    },
    views: [{ id: "entries.list", collection: "entries", default_order: orderBy("title"), max_limit: 50 }],
    actions: {
      update_entry: (input, store) => {
        const changes = input.changes as Record<string, unknown>;
        if (typeof changes.amount === "number" && changes.amount > 1000) throw new Error("entries.amount must be at most 1000");
        const row = store.update("entries", String(input.id), Number(input.expected_revision), changes);
        return { id: row.id, revision: row.revision };
      },
      set_status: (input, store) => {
        const row = store.update("entries", String(input.id), Number(input.expected_revision), { status: input.status, reason: input.reason || null });
        return { revision: row.revision };
      },
    },
  });
}

const rowTitles = () =>
  screen
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell")[0].textContent?.replace(", open details", ""));

describe("list, filter, detail and failed-save recovery through the bridge", () => {
  it("filters, sorts, pages and edits by keyboard; a failed save keeps the draft", async () => {
    const memory = await app();
    const user = userEvent.setup();
    render(
      <AlphaProvider client={memory.client}>
        <ListScreen />
      </AlphaProvider>,
    );
    await waitFor(() => expect(rowTitles()).toEqual(["Alpha paper", "Blue pens", "Coffee filters"]));
    await user.click(screen.getByRole("button", { name: "Next page" }));
    await waitFor(() => expect(rowTitles()).toEqual(["Desk lamp"]));
    await user.click(screen.getByRole("button", { name: "Previous page" }));

    // Filter by keyboard: type in search, then choose a kind.
    await user.type(screen.getByLabelText("Search titles"), "e");
    await user.selectOptions(screen.getByLabelText("Kind"), "task");
    await waitFor(() => expect(rowTitles()).toEqual(["Blue pens", "Coffee filters"]));
    expect(screen.getByRole("status", { name: "" })).toBeDefined();

    // Sort: the heading button toggles direction and aria-sort follows.
    const titleHeader = screen.getByRole("columnheader", { name: /Title/ });
    expect(titleHeader).toHaveAttribute("aria-sort", "ascending");
    await user.click(within(titleHeader).getByRole("button"));
    await waitFor(() => expect(rowTitles()).toEqual(["Coffee filters", "Blue pens"]));
    expect(titleHeader).toHaveAttribute("aria-sort", "descending");

    // Open a row with the keyboard.
    const open = screen.getByRole("button", { name: "Blue pens, open details" });
    open.focus();
    await user.keyboard("{Enter}");
    const dialog = await screen.findByRole("dialog", { name: "Blue pens" });
    const amount = within(dialog).getByLabelText("Amount");
    await user.clear(amount);
    await user.type(amount, "5000");
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));
    expect(await within(dialog).findByText(/Not saved\. Amount must be at most 1000/)).toBeInTheDocument();
    expect(amount).toHaveValue("5000");
    const pens = memory.store.records.entries.find((r) => r.values.title === "Blue pens")!;
    expect(pens.values.amount).toBe(7);
    expect(pens.revision).toBe(1);

    // Correct and retry by keyboard: the committed value shows after the save.
    await user.clear(amount);
    await user.type(amount, "12{Enter}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(pens.values.amount).toBe(12);
    expect(pens.revision).toBe(2);
    await waitFor(() => expect(screen.getByRole("row", { name: /Blue pens/ })).toHaveTextContent("12"));

    // Clear filters restores the full first page.
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(rowTitles()).toEqual(["Desk lamp", "Coffee filters", "Blue pens"]));
  });

  it("shows empty and error states", async () => {
    const memory = await createMemoryApp({ views: [{ id: "entries.list", collection: "entries" }] });
    render(
      <AlphaProvider client={memory.client}>
        <ListScreen />
      </AlphaProvider>,
    );
    expect(await screen.findByText("No entries match")).toBeInTheDocument();
    memory.revoke("closed for test");
    await userEvent.setup().type(screen.getByLabelText("Search titles"), "x");
    expect(await screen.findByText(/Entries could not be loaded/)).toBeInTheDocument();
  });
});

function Queue() {
  const view = useView<Entry>("entries.list", { where: eq("status", "new"), limit: 50 });
  const decide = useAction("set_status");
  return (
    <ReviewQueue<RecordRow<Entry>>
      items={view.records}
      getId={(r) => r.id}
      getLabel={(r) => r.values.title}
      renderItem={(r) => <p>{r.values.title}</p>}
      decisions={[
        { id: "kept", label: "Keep", doneLabel: "Kept", variant: "primary" },
        { id: "dismissed", label: "Dismiss", doneLabel: "Dismissed" },
      ]}
      decisionOf={(r) => (r.values.status && r.values.status !== "new" ? r.values.status : null)}
      onDecide={async (r, decision, reason) => void (await decide.run({ id: r.id, expected_revision: r.revision, status: decision, reason }))}
      reasonLabel="Reason (optional)"
      bulk={{ decisionId: "dismissed" }}
    />
  );
}

describe("review queue", () => {
  it("decides by keyboard, preserves decisions and confirms bulk actions", async () => {
    const memory = await app();
    const user = userEvent.setup();
    render(
      <AlphaProvider client={memory.client}>
        <Queue />
      </AlphaProvider>,
    );
    const card = await screen.findByRole("group", { name: /Alpha paper, not decided/ });
    card.focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("group", { name: /Blue pens/ })).toBeInTheDocument();
    await user.keyboard("{ArrowLeft}");
    await user.type(screen.getByLabelText("Reason (optional)"), "useful");
    screen.getByRole("group", { name: /Alpha paper/ }).focus();
    await user.keyboard("1");
    expect(await screen.findByText("Kept: Alpha paper")).toBeInTheDocument();
    const paper = memory.store.records.entries.find((r) => r.values.title === "Alpha paper")!;
    expect(paper.values).toMatchObject({ status: "kept", reason: "useful" });

    // Bulk dismiss needs an explicit confirmation.
    await user.click(screen.getByRole("button", { name: /Dismiss all 2 undecided/ }));
    expect(memory.store.records.entries.filter((r) => r.values.status === "dismissed")).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Yes, dismiss 2" }));
    try {
      await screen.findByText("Dismissed 2 items", {}, { timeout: 3000 });
    } catch (error) {
      console.log("DIAG", document.body.textContent?.slice(0, 600), JSON.stringify(memory.store.records.entries.map((r) => [r.values.title, r.values.status, r.revision])));
      throw error;
    }
    expect(memory.store.records.entries.filter((r) => r.values.status === "new")).toHaveLength(0);
  });

  it("reports a failed decision and leaves the item undecided", async () => {
    const memory = await app();
    const user = userEvent.setup();
    render(
      <AlphaProvider client={memory.client}>
        <Queue />
      </AlphaProvider>,
    );
    await screen.findByRole("group", { name: /Alpha paper/ });
    memory.failNext("set_status", "The App is not available right now.");
    await user.click(screen.getByRole("button", { name: /Keep/ }));
    expect(await screen.findByText(/Not saved for Alpha paper: The App is not available right now/)).toBeInTheDocument();
    expect(screen.getByRole("group", { name: /Alpha paper, not decided/ })).toBeInTheDocument();
  });
});
