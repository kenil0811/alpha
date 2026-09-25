// Neutral composition B: add entries quickly, correct today's, and see totals and a daily trend.
// Uses only the interaction kit and the entries fixture's declared views and actions.
import { StrictMode, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "@alpha/ui-kit/styles.css";
import {
  AlphaApp,
  Button,
  Cluster,
  Columns,
  DetailDrawer,
  Form,
  LoadingState,
  MetricCard,
  NumberField,
  OperationStatus,
  Page,
  QuickEntry,
  RangeSelect,
  RecordTable,
  Section,
  TextField,
  TrendChart,
  addDays,
  daySeries,
  eq,
  formatNumber,
  gte,
  orderBy,
  parseNumber,
  today,
  useAction,
  useAggregate,
  useView,
  type ParseResult,
  type RecordRow,
} from "@alpha/ui-kit";

type Entry = { title: string; amount?: number; kind: string; status: string; noted_on: string };
type Draft = { title: string; amount: number | null };

/** "3 paper", "paper 3" or "paper" (no amount). The amount limit is the App's, checked there. */
export function parseEntry(text: string): ParseResult<Draft> {
  const trimmed = text.trim();
  if (!trimmed) return { status: "empty" };
  if (trimmed.length > 120) return { status: "invalid", message: "Keep it under 120 characters." };
  const leading = trimmed.match(/^(\d+(?:[.,]\d+)?)\s+(.+)$/);
  const trailing = trimmed.match(/^(.+?)\s+(\d+(?:[.,]\d+)?)$/);
  const match = leading ? { amount: leading[1], title: leading[2] } : trailing ? { amount: trailing[2], title: trailing[1] } : null;
  if (match) {
    const amount = Number(match.amount.replace(",", "."));
    return { status: "ok", value: { title: match.title, amount }, summary: `${match.title} (${formatNumber(amount)})` };
  }
  return { status: "ambiguous", value: { title: trimmed, amount: null }, summary: trimmed, note: "No amount found; it will be saved without one." };
}

function CorrectEntry({ entry, onDone }: { entry: RecordRow<Entry>; onDone: () => void }) {
  const save = useAction("update_entry");
  const remove = useAction("remove_entry");
  const [title, setTitle] = useState(entry.values.title);
  const [amount, setAmount] = useState(entry.values.amount === undefined ? "" : String(entry.values.amount));
  const parsed = parseNumber(amount);
  return (
    <Form
      onSubmit={async () => {
        if (!parsed.ok || !title.trim()) return;
        try {
          await save.run({ id: entry.id, expected_revision: entry.revision, changes: { title: title.trim(), amount: parsed.value } });
          onDone();
        } catch {
          // shown by OperationStatus; the draft stays for another try
        }
      }}
    >
      <TextField label="Title" value={title} onChange={(e) => setTitle(e.target.value)} required error={title.trim() ? null : "Give the entry a title."} />
      <NumberField label="Amount" value={amount} onValueChange={setAmount} error={parsed.ok ? null : parsed.message} />
      <Cluster>
        <Button type="submit" variant="primary" busy={save.state === "saving"} busyLabel="Saving…">
          Save
        </Button>
        <Button
          variant="danger"
          busy={remove.state === "saving"}
          busyLabel="Removing…"
          onClick={async () => {
            try {
              await remove.run({ id: entry.id, expected_revision: entry.revision });
              onDone();
            } catch {
              // shown below
            }
          }}
        >
          Remove
        </Button>
      </Cluster>
      <OperationStatus state={save.state} error={save.error} />
      {remove.state === "failed" ? <OperationStatus state="failed" error={remove.error} /> : null}
    </Form>
  );
}

function Today() {
  const day = today();
  const add = useAction<{ id: string; revision: number }>("add_entry");
  const remove = useAction("remove_entry");
  const entries = useView<Entry>("entries.list", { where: eq("noted_on", day), order_by: orderBy("-created_at"), limit: 50 });
  const [open, setOpen] = useState<RecordRow<Entry> | null>(null);
  const total = entries.records.reduce((sum, r) => sum + (r.values.amount ?? 0), 0);
  const withAmount = entries.records.filter((r) => r.values.amount !== undefined).length;
  return (
    <Section title="Today" description="Type an entry and press Enter. Open one to correct it.">
      <QuickEntry<Draft>
        label="Add an entry"
        placeholder="For example: 3 paper"
        hint="Start or end with a number to record an amount."
        parse={parseEntry}
        autoFocus
        onSubmit={async (draft) => {
          const created = await add.run({ title: draft.title, amount: draft.amount });
          return { undo: async () => void (await remove.run({ id: created.id, expected_revision: created.revision })) };
        }}
      />
      <div className="a-metrics">
        <MetricCard
          label="Total today"
          value={entries.loading ? null : total}
          hint={`${entries.records.length} ${entries.records.length === 1 ? "entry" : "entries"}`}
        />
        <MetricCard label="Entries with an amount" value={entries.loading ? null : withAmount} />
      </div>
      <RecordTable<RecordRow<Entry>>
        caption="Today's entries"
        columns={[
          { id: "title", header: "Title", cell: (r) => r.values.title },
          { id: "amount", header: "Amount", cell: (r) => formatNumber(r.values.amount), numeric: true },
        ]}
        rows={entries.records}
        getRowId={(r) => r.id}
        getRowLabel={(r) => r.values.title}
        onOpen={setOpen}
        loading={entries.loading}
        error={entries.error}
        onRetry={entries.refresh}
        empty={{ title: "Nothing recorded today", message: "Your first entry will appear here." }}
      />
      <DetailDrawer open={open !== null} onClose={() => setOpen(null)} title={open ? `Correct “${open.values.title}”` : ""}>
        {open ? <CorrectEntry key={`${open.id}:${open.revision}`} entry={open} onDone={() => setOpen(null)} /> : null}
      </DetailDrawer>
    </Section>
  );
}

function Trend() {
  const [days, setDays] = useState(14);
  const end = today();
  const start = addDays(end, -(days - 1));
  const daily = useAggregate("entries.daily", gte("noted_on", start));
  const points = useMemo(() => {
    const values = new Map<string, number | null>();
    for (const group of daily.groups) {
      const key = String(group.key.noted_on_day);
      const value = group.values.total;
      values.set(key, typeof value === "number" ? value : 0);
    }
    return daySeries(end, days, values);
  }, [daily.groups, end, days]);
  const recorded = points.filter((p) => p.value !== null);
  const average = recorded.length ? recorded.reduce((sum, p) => sum + (p.value ?? 0), 0) / recorded.length : null;
  return (
    <Section title="Trend" description="Daily totals. Days with no entries are shown as gaps, not zero.">
      <div className="a-metrics">
        <MetricCard label={`Average on days with entries (last ${days})`} value={daily.loading ? null : average} hint={`${recorded.length} of ${days} days have entries`} />
      </div>
      {daily.error ? (
        <OperationStatus state="failed" error={daily.error} onRetry={daily.refresh} />
      ) : daily.loading && daily.groups.length === 0 ? (
        <LoadingState label="Loading the trend…" />
      ) : (
        <TrendChart title="Daily total" points={points} controls={<RangeSelect value={days} onChange={setDays} />} />
      )}
    </Section>
  );
}

function App() {
  return (
    <Page title="Daily entries" description="Add entries quickly and see how the totals change day by day.">
      <Columns>
        <Today />
        <Trend />
      </Columns>
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
