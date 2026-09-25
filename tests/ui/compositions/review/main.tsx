// Neutral composition A: browse, filter, inspect and correct entries, and review new ones.
// Uses only the interaction kit and the entries fixture's declared views and actions.
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import "@alpha/ui-kit/styles.css";
import {
  AlphaApp,
  Button,
  Cluster,
  DetailDrawer,
  Form,
  DetailList,
  FilterBar,
  NumberField,
  OperationStatus,
  Page,
  Pager,
  ProvenanceNote,
  RecordTable,
  ReviewQueue,
  Section,
  SelectField,
  TextAreaField,
  TextField,
  allOf,
  contains,
  eq,
  formatDay,
  formatNumber,
  orderBy,
  parseNumber,
  useAction,
  useView,
  type FilterValues,
  type RecordRow,
  type SortState,
} from "@alpha/ui-kit";

type Entry = {
  title: string;
  amount?: number;
  kind: string;
  status: string;
  noted_on: string;
  note?: string;
  reason?: string;
};

const KINDS = [
  { value: "note", label: "Note" },
  { value: "task", label: "Task" },
  { value: "idea", label: "Idea" },
];
const STATUSES = [
  { value: "new", label: "New" },
  { value: "kept", label: "Kept" },
  { value: "dismissed", label: "Dismissed" },
];
const label = (options: typeof KINDS, value: string) => options.find((o) => o.value === value)?.label ?? value;
const PAGE = 10;

function EntryEditor({ entry, onSaved }: { entry: RecordRow<Entry>; onSaved: () => void }) {
  const save = useAction("update_entry");
  const [title, setTitle] = useState(entry.values.title);
  const [amount, setAmount] = useState(entry.values.amount === undefined ? "" : String(entry.values.amount));
  const [kind, setKind] = useState(entry.values.kind);
  const [note, setNote] = useState(entry.values.note ?? "");
  const parsedAmount = parseNumber(amount);
  const titleError = title.trim() ? null : "Give the entry a title.";
  const canSave = parsedAmount.ok && !titleError;
  return (
    <Form
      onSubmit={async () => {
        if (!canSave) return;
        try {
          await save.run({
            id: entry.id,
            expected_revision: entry.revision,
            changes: { title: title.trim(), amount: parsedAmount.ok ? parsedAmount.value : null, kind, note: note.trim() || null },
          });
          onSaved();
        } catch {
          // OperationStatus shows why; the draft stays so it can be corrected and saved again.
        }
      }}
    >
      <TextField label="Title" value={title} onChange={(e) => setTitle(e.target.value)} required error={titleError} />
      <NumberField label="Amount" value={amount} onValueChange={setAmount} error={parsedAmount.ok ? null : parsedAmount.message} hint="Leave empty if there is no amount." />
      <ProvenanceNote provenance={entry.provenance.amount} formatPrevious={(v) => formatNumber(Number(v))} />
      <SelectField label="Kind" value={kind} onChange={(e) => setKind(e.target.value)} options={KINDS} />
      <TextAreaField label="Note" value={note} onChange={(e) => setNote(e.target.value)} />
      <Cluster>
        <Button type="submit" variant="primary" busy={save.state === "saving"} busyLabel="Saving…" disabled={!canSave}>
          Save changes
        </Button>
      </Cluster>
      <OperationStatus state={save.state} error={save.error} />
    </Form>
  );
}

function AllEntries() {
  const [filters, setFilters] = useState<FilterValues>({ search: "", kind: "", status: "" });
  const [sort, setSort] = useState<SortState>({ field: "created_at", direction: "desc" });
  const [open, setOpen] = useState<RecordRow<Entry> | null>(null);
  const view = useView<Entry>("entries.list", {
    where: allOf(
      filters.search ? contains("title", filters.search) : undefined,
      filters.kind ? eq("kind", filters.kind) : undefined,
      filters.status ? eq("status", filters.status) : undefined,
    ),
    order_by: orderBy(sort.direction === "desc" ? `-${sort.field}` : sort.field),
    limit: PAGE,
  });
  const first = view.page * PAGE + 1;
  return (
    <Section title="All entries" description="Search, filter and sort; open an entry to see or correct it.">
      <FilterBar
        searchLabel="Search titles"
        searchPlaceholder="Type part of a title"
        filters={[
          { id: "kind", label: "Kind", options: KINDS },
          { id: "status", label: "Status", options: STATUSES },
        ]}
        values={filters}
        onChange={setFilters}
        resultLabel={view.loading ? "Loading…" : view.records.length ? `Showing ${first}–${first + view.records.length - 1}${view.hasNext ? " (more on the next page)" : ""}` : "No matches"}
      />
      <RecordTable<RecordRow<Entry>>
        caption="Entries"
        columns={[
          { id: "title", header: "Title", cell: (r) => r.values.title, sortField: "title" },
          { id: "amount", header: "Amount", cell: (r) => formatNumber(r.values.amount), numeric: true, sortField: "amount" },
          { id: "kind", header: "Kind", cell: (r) => label(KINDS, r.values.kind), sortField: "kind" },
          { id: "status", header: "Status", cell: (r) => label(STATUSES, r.values.status), sortField: "status" },
          { id: "day", header: "Day", cell: (r) => formatDay(r.values.noted_on), sortField: "noted_on" },
        ]}
        rows={view.records}
        getRowId={(r) => r.id}
        getRowLabel={(r) => r.values.title}
        onOpen={setOpen}
        sort={sort}
        onSortChange={setSort}
        loading={view.loading}
        error={view.error}
        onRetry={view.refresh}
        empty={{
          title: filters.search || filters.kind || filters.status ? "No entries match these filters" : "No entries yet",
          message: filters.search || filters.kind || filters.status ? "Clear the filters to see every entry." : "Entries you add will appear here.",
        }}
        footer={<Pager label={`Page ${view.page + 1}`} hasPrevious={view.hasPrevious} hasNext={view.hasNext} onPrevious={view.previous} onNext={view.next} busy={view.loading} />}
      />
      <DetailDrawer
        open={open !== null}
        onClose={() => setOpen(null)}
        title={open?.values.title ?? ""}
        description={open ? `${label(KINDS, open.values.kind)} · ${formatDay(open.values.noted_on)} · ${label(STATUSES, open.values.status)}` : null}
      >
        {open ? (
          <>
            <DetailList
              items={[
                { label: "Status", value: label(STATUSES, open.values.status) },
                { label: "Reason", value: open.values.reason ?? "—" },
                { label: "Added", value: new Date(open.created_at).toLocaleString() },
              ]}
            />
            <EntryEditor key={`${open.id}:${open.revision}`} entry={open} onSaved={() => setOpen(null)} />
          </>
        ) : null}
      </DetailDrawer>
    </Section>
  );
}

function ReviewNew() {
  const view = useView<Entry>("entries.queue", { limit: 200 });
  const decide = useAction("set_status");
  return (
    <Section title="Review new entries" description="Keep or dismiss each entry; decisions are saved and stay visible.">
      <ReviewQueue<RecordRow<Entry>>
        items={view.records}
        getId={(r) => r.id}
        getLabel={(r) => r.values.title}
        renderItem={(r) => (
          <DetailList
            items={[
              { label: "Title", value: r.values.title },
              { label: "Amount", value: formatNumber(r.values.amount) },
              { label: "Kind", value: label(KINDS, r.values.kind) },
              { label: "Day", value: formatDay(r.values.noted_on) },
              ...(r.values.reason ? [{ label: "Reason", value: r.values.reason }] : []),
            ]}
          />
        )}
        decisions={[
          { id: "kept", label: "Keep", doneLabel: "Kept", variant: "primary" },
          { id: "dismissed", label: "Dismiss", doneLabel: "Dismissed" },
        ]}
        decisionOf={(r) => (r.values.status === "new" ? null : r.values.status)}
        onDecide={async (r, decision, reason) => {
          await decide.run({ id: r.id, expected_revision: r.revision, status: decision, ...(reason.trim() ? { reason } : {}) });
        }}
        reasonLabel="Reason (optional)"
        bulk={{ decisionId: "dismissed" }}
        empty={{ title: "Nothing to review", message: "New entries will wait here for a decision." }}
      />
    </Section>
  );
}

function App() {
  return (
    <Page title="Entries" description="Review, filter and correct what has been recorded.">
      <AllEntries />
      <ReviewNew />
    </Page>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AlphaApp>
      <App />
    </AlphaApp>
  </StrictMode>,
);
