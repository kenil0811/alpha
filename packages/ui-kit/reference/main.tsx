// Kit reference sheet: every pattern with neutral data, in populated, empty, loading and failing
// states, with an optional long-label mode. Development only; it is not packed.
import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import axe from "axe-core";
import "../styles/kit.css";
import {
  AlphaProvider,
  Badge,
  Button,
  CheckboxField,
  Cluster,
  Columns,
  DateField,
  DetailDrawer,
  DetailList,
  EmptyState,
  ErrorState,
  FilterBar,
  Form,
  LoadingState,
  MetricCard,
  NumberField,
  OperationStatus,
  Page,
  Pager,
  ProvenanceNote,
  QuickEntry,
  RangeSelect,
  RecordTable,
  ReviewQueue,
  Section,
  SelectField,
  StatusMessage,
  TextAreaField,
  TextField,
  TrendChart,
  addDays,
  allOf,
  contains,
  daySeries,
  eq,
  formatDay,
  formatNumber,
  gte,
  orderBy,
  parseNumber,
  today,
  useAction,
  useAggregate,
  useView,
  type FilterValues,
  type RecordRow,
  type SortState,
} from "../src";
import { createMemoryApp, type MemoryApp, type Values } from "../src/testing";

type Mode = "populated" | "empty" | "loading" | "failing";
type Row = { title: string; amount?: number; group: string; state: string; day: string };

const LONG = "an unusually long label that someone might genuinely write to describe what they are tracking";

function sample(long: boolean): Values[] {
  const rows: Values[] = [];
  const groups = ["first", "second", "third"];
  for (let i = 0; i < 18; i += 1) {
    if (i % 5 === 3) continue;
    rows.push({
      title: long && i % 4 === 0 ? `Item ${i + 1}, ${LONG}` : `Item ${i + 1}`,
      amount: i % 6 === 0 ? undefined : (i * 3) % 11,
      group: groups[i % 3],
      state: i < 6 ? "open" : i % 2 ? "accepted" : "declined",
      day: addDays(today(), -Math.floor(i / 2)),
    });
  }
  return rows.map((r) => Object.fromEntries(Object.entries(r).filter(([, v]) => v !== undefined)));
}

async function makeApp(mode: Mode, long: boolean): Promise<MemoryApp> {
  const memory = await createMemoryApp({
    collections: { rows: mode === "empty" ? [] : sample(long) },
    queryLatencyMs: mode === "loading" ? 1_000_000_000 : 0,
    latencyMs: 250,
    views: [
      { id: "rows.list", collection: "rows", default_order: orderBy("-day"), max_limit: 100 },
      { id: "rows.daily", kind: "aggregate", collection: "rows", group_by: [{ field: "day", bucket: "day" }], metrics: [{ name: "total", fn: "sum", field: "amount" }] },
    ],
    actions: {
      add_row: (input, store) => {
        const row = store.create("rows", { ...input, group: "first", state: "open", day: today() });
        return { id: row.id, revision: row.revision };
      },
      update_row: (input, store) => {
        const changes = input.changes as Values;
        if (typeof changes.amount === "number" && changes.amount > 100) throw new Error("rows.amount must be at most 100");
        const row = store.update("rows", String(input.id), Number(input.expected_revision), changes);
        return { id: row.id, revision: row.revision };
      },
      decide_row: (input, store) => {
        const row = store.update("rows", String(input.id), Number(input.expected_revision), { state: input.state });
        return { revision: row.revision };
      },
      remove_row: (input, store) => {
        store.remove("rows", String(input.id), Number(input.expected_revision));
        return {};
      },
    },
  });
  if (mode === "failing") {
    memory.failQueries("The App is not available right now.");
  }
  return memory;
}

const GROUPS = [
  { value: "first", label: "First" },
  { value: "second", label: "Second" },
  { value: "third", label: "Third" },
];

function Editor({ row, onDone, long }: { row: RecordRow<Row>; onDone: () => void; long: boolean }) {
  const save = useAction("update_row");
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
          /* shown below */
        }
      }}
    >
      <TextField label={long ? `Title, ${LONG}` : "Title"} value={title} onChange={(e) => setTitle(e.target.value)} required />
      <NumberField label="Amount" value={amount} onValueChange={setAmount} error={parsed.ok ? null : parsed.message} hint="Up to 100. Try 500 to see a failed save." />
      <ProvenanceNote provenance={{ source: "model_estimate" }} />
      <Button type="submit" variant="primary" busy={save.state === "saving"} busyLabel="Saving…">
        Save changes
      </Button>
      <OperationStatus state={save.state} error={save.error} />
    </Form>
  );
}

function ListPattern({ long }: { long: boolean }) {
  const [filters, setFilters] = useState<FilterValues>({ search: "", group: "" });
  const [sort, setSort] = useState<SortState>({ field: "day", direction: "desc" });
  const [open, setOpen] = useState<RecordRow<Row> | null>(null);
  const view = useView<Row>("rows.list", {
    where: allOf(filters.search ? contains("title", filters.search) : undefined, filters.group ? eq("group", filters.group) : undefined),
    order_by: orderBy(sort.direction === "desc" ? `-${sort.field}` : sort.field),
    limit: 6,
  });
  return (
    <Section title={long ? `List, filter and detail: ${LONG}` : "List, filter and detail"} description="FilterBar, RecordTable, Pager and DetailDrawer.">
      <FilterBar
        searchLabel={long ? `Search ${LONG}` : "Search titles"}
        filters={[{ id: "group", label: "Group", options: GROUPS }]}
        values={filters}
        onChange={setFilters}
        resultLabel={view.loading ? "Loading…" : `${view.records.length} shown`}
      />
      <RecordTable<RecordRow<Row>>
        caption="Items"
        columns={[
          { id: "title", header: long ? `Title of ${LONG}` : "Title", cell: (r) => r.values.title, sortField: "title" },
          { id: "amount", header: "Amount", cell: (r) => formatNumber(r.values.amount), numeric: true, sortField: "amount" },
          { id: "group", header: "Group", cell: (r) => r.values.group },
          { id: "day", header: "Day", cell: (r) => formatDay(r.values.day), sortField: "day" },
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
        empty={{ title: "Nothing here yet", message: "Items you add appear here." }}
        footer={<Pager label={`Page ${view.page + 1}`} hasPrevious={view.hasPrevious} hasNext={view.hasNext} onPrevious={view.previous} onNext={view.next} />}
      />
      <DetailDrawer open={open !== null} onClose={() => setOpen(null)} title={open?.values.title ?? ""}>
        {open ? (
          <>
            <DetailList items={[{ label: "Group", value: open.values.group }, { label: "Day", value: formatDay(open.values.day) }]} />
            <Editor key={open.id + open.revision} row={open} onDone={() => setOpen(null)} long={long} />
          </>
        ) : null}
      </DetailDrawer>
    </Section>
  );
}

function EntryPattern() {
  const add = useAction<{ id: string; revision: number }>("add_row");
  const remove = useAction("remove_row");
  return (
    <Section title="Quick entry" description="Type “3 paper” and press Enter; Undo removes it.">
      <QuickEntry<{ title: string; amount: number | null }>
        label="Add an item"
        placeholder="For example: 3 paper"
        parse={(text) => {
          const t = text.trim();
          if (!t) return { status: "empty" };
          const m = t.match(/^(\d+)\s+(.+)$/);
          return m
            ? { status: "ok", value: { title: m[2], amount: Number(m[1]) }, summary: `${m[2]} (${m[1]})` }
            : { status: "ambiguous", value: { title: t, amount: null }, summary: t, note: "No amount found." };
        }}
        onSubmit={async (value) => {
          const created = await add.run(value);
          return { undo: async () => void (await remove.run({ id: created.id, expected_revision: created.revision })) };
        }}
      />
    </Section>
  );
}

function ReviewPattern() {
  const view = useView<Row>("rows.list", { order_by: orderBy("day"), limit: 100 });
  const decide = useAction("decide_row");
  return (
    <Section title="Review queue" description="Focus the card, then use ← → and 1 or 2.">
      <ReviewQueue<RecordRow<Row>>
        items={view.records}
        getId={(r) => r.id}
        getLabel={(r) => r.values.title}
        renderItem={(r) => <DetailList items={[{ label: "Title", value: r.values.title }, { label: "Amount", value: formatNumber(r.values.amount) }]} />}
        decisions={[
          { id: "accepted", label: "Accept", doneLabel: "Accepted", variant: "primary" },
          { id: "declined", label: "Decline", doneLabel: "Declined" },
        ]}
        decisionOf={(r) => (r.values.state === "open" ? null : r.values.state)}
        onDecide={async (r, state) => void (await decide.run({ id: r.id, expected_revision: r.revision, state }))}
        reasonLabel="Reason (optional)"
        bulk={{ decisionId: "declined" }}
      />
    </Section>
  );
}

function TrendPattern() {
  const [days, setDays] = useState(14);
  const end = today();
  const daily = useAggregate("rows.daily", gte("day", addDays(end, -(days - 1))));
  const points = useMemo(
    () => daySeries(end, days, new Map(daily.groups.map((g) => [String(g.key.day_day), typeof g.values.total === "number" ? g.values.total : 0]))),
    [daily.groups, end, days],
  );
  const recorded = points.filter((p) => p.value !== null);
  return (
    <Section title="Metrics and trend" description="Missing days are gaps, not zero.">
      <div className="a-metrics">
        <MetricCard label="Total" value={daily.loading ? null : recorded.reduce((s, p) => s + (p.value ?? 0), 0)} unit="units" />
        <MetricCard label="Days with entries" value={daily.loading ? null : recorded.length} hint={`of ${days}`} />
      </div>
      {daily.error ? (
        <OperationStatus state="failed" error={daily.error} onRetry={daily.refresh} />
      ) : daily.loading ? (
        <LoadingState label="Loading the trend…" />
      ) : (
        <TrendChart title="Daily total" unit="units" points={points} controls={<RangeSelect value={days} onChange={setDays} />} />
      )}
    </Section>
  );
}

function StatesGallery({ long }: { long: boolean }) {
  return (
    <Section title="Feedback states" description="Every status has an icon and words, never color alone.">
      <StatusMessage tone="info">{long ? LONG : "Informational note."}</StatusMessage>
      <StatusMessage tone="success">Saved.</StatusMessage>
      <StatusMessage tone="warning">Check this value.</StatusMessage>
      <StatusMessage tone="danger">Not saved. The App is not available right now.</StatusMessage>
      <Cluster>
        <Badge>Not decided</Badge>
        <Badge tone="info">You corrected</Badge>
        <Badge tone="warning">Estimate</Badge>
        <Badge tone="success">Accepted</Badge>
        <Badge tone="danger">Failed</Badge>
      </Cluster>
      <OperationStatus state="saving" />
      <OperationStatus state="saved" />
      <OperationStatus state="failed" error="Amount must be at most 100" onRetry={() => undefined} />
      <EmptyState title="Nothing yet" message="The first entry will appear here." action={<Button>Add one</Button>} />
      <LoadingState label="Loading items…" />
      <ErrorState message="The App is not available right now." onRetry={() => undefined} />
    </Section>
  );
}

function FormsGallery({ long }: { long: boolean }) {
  const [amount, setAmount] = useState("3.5");
  const parsed = parseNumber(amount);
  return (
    <Section title="Form controls" description="Labels, hints, required marks and errors.">
      <Form onSubmit={() => undefined}>
        <TextField label={long ? LONG : "Name"} required hint="As you would say it." />
        <TextField label="With an error" defaultValue="" error="Give this a name." required />
        <NumberField label="Amount" unit="units" value={amount} onValueChange={setAmount} error={parsed.ok ? null : parsed.message} />
        <DateField label="Day" defaultValue={today()} />
        <SelectField label="Group" options={GROUPS} emptyLabel="Not set" />
        <TextAreaField label="Note" />
        <CheckboxField label={long ? LONG : "Remember this choice"} />
        <Cluster>
          <Button type="submit" variant="primary">Primary</Button>
          <Button>Secondary</Button>
          <Button variant="danger">Remove</Button>
          <Button variant="ghost">Ghost</Button>
          <Button busy busyLabel="Saving…">Busy</Button>
        </Cluster>
      </Form>
    </Section>
  );
}

function Reference() {
  const params = new URLSearchParams(window.location.search);
  const [mode, setMode] = useState<Mode>((params.get("mode") as Mode) || "populated");
  const [long, setLong] = useState(params.get("long") === "1");
  const [memory, setMemory] = useState<MemoryApp | null>(null);
  useEffect(() => {
    let cancelled = false;
    setMemory(null);
    void makeApp(mode, long).then((app) => {
      if (!cancelled) setMemory(app);
    });
    return () => {
      cancelled = true;
    };
  }, [mode, long]);
  return (
    <Page
      title="Interaction kit reference"
      description="Neutral data; every pattern in populated, empty, loading and failing states."
      actions={
        <Cluster>
          <SelectField
            label="Data state"
            value={mode}
            onChange={(e) => setMode(e.target.value as Mode)}
            options={[
              { value: "populated", label: "Populated" },
              { value: "empty", label: "Empty" },
              { value: "loading", label: "Loading" },
              { value: "failing", label: "Failing" },
            ]}
          />
          <CheckboxField label="Long labels" checked={long} onChange={(e) => setLong(e.target.checked)} />
        </Cluster>
      }
    >
      {memory ? (
        <AlphaProvider client={memory.client} key={`${mode}-${long}`}>
          <Columns>
            <EntryPattern />
            <TrendPattern />
          </Columns>
          <ListPattern long={long} />
          <ReviewPattern />
          <Columns>
            <FormsGallery long={long} />
            <StatesGallery long={long} />
          </Columns>
        </AlphaProvider>
      ) : (
        <LoadingState label="Preparing example data…" />
      )}
    </Page>
  );
}

declare global {
  interface Window {
    __alphaAxe?: () => Promise<Array<{ id: string; impact: string | null | undefined; nodes: number; targets: string[] }>>;
  }
}
window.__alphaAxe = async () => {
  const result = await axe.run(document);
  return result.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, targets: v.nodes.slice(0, 5).map((n) => n.target.join(" ")) }));
};

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Reference />
  </StrictMode>,
);
