import { render, screen, within } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it } from "vitest";
import { daySeries } from "../format";
import { Button, CheckboxField, DateField, NumberField, SelectField, TextAreaField, TextField } from "./controls";
import { DetailDrawer, DetailList } from "./DetailDrawer";
import { Badge, EmptyState, ErrorState, LoadingState, OperationStatus, ProvenanceNote, StatusMessage } from "./feedback";
import { FilterBar } from "./FilterBar";
import { Columns, Page, Section } from "./layout";
import { QuickEntry } from "./QuickEntry";
import { Pager, RecordTable } from "./RecordTable";
import { ReviewQueue } from "./ReviewQueue";
import { MetricCard, RangeSelect, TrendChart } from "./Trend";

const LONG = "A very long label that someone might really write for a field when describing what they want to track every single day";

async function violations(container: HTMLElement) {
  // jsdom has no layout or computed colors; contrast is covered by tokens.test.ts and the
  // rendered checks in a real browser.
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  return result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

type Row = { id: string; title: string; amount: number | null };
const ROWS: Row[] = [
  { id: "r1", title: LONG, amount: 3 },
  { id: "r2", title: "Short", amount: null },
];

function Everything({ state }: { state: "populated" | "empty" | "loading" | "failed" }) {
  const rows = state === "populated" ? ROWS : [];
  return (
    <Page title={LONG} description={LONG} actions={<Button variant="primary">Add</Button>}>
      <Columns>
        <Section title={LONG} description={LONG}>
          <QuickEntry label={LONG} parse={(t) => (t ? { status: "ok", value: t, summary: t } : { status: "empty" })} onSubmit={async () => undefined} />
          <FilterBar
            searchLabel={LONG}
            filters={[{ id: "kind", label: LONG, options: [{ value: "a", label: LONG }] }]}
            values={{ search: "", kind: "" }}
            onChange={() => undefined}
            resultLabel="2 shown"
          />
          <RecordTable<Row>
            caption={LONG}
            columns={[
              { id: "title", header: LONG, cell: (r) => r.title, sortField: "title" },
              { id: "amount", header: "Amount", cell: (r) => r.amount ?? "No entry", numeric: true },
            ]}
            rows={rows}
            getRowId={(r) => r.id}
            getRowLabel={(r) => r.title}
            onOpen={() => undefined}
            sort={{ field: "title", direction: "asc" }}
            onSortChange={() => undefined}
            selectedIds={new Set(["r1"])}
            onSelectionChange={() => undefined}
            loading={state === "loading"}
            error={state === "failed" ? "The App is not available right now." : null}
            onRetry={() => undefined}
            empty={{ title: "Nothing yet", message: "Add the first entry above." }}
            footer={<Pager label="Showing 1–2" hasPrevious={false} hasNext onPrevious={() => undefined} onNext={() => undefined} />}
          />
        </Section>
        <Section title="Details">
          <TextField label={LONG} error="Required" required />
          <NumberField label="Amount" unit="units" value="3" onValueChange={() => undefined} hint="Whole or decimal numbers" />
          <DateField label="Day" />
          <SelectField label="Kind" options={[{ value: "a", label: "A" }]} emptyLabel="Not set" />
          <TextAreaField label="Note" />
          <CheckboxField label={LONG} />
          <DetailList items={[{ label: LONG, value: LONG }]} />
          <ProvenanceNote provenance={{ source: "model_estimate" }} />
          <ProvenanceNote provenance={{ source: "user_correction", previous: { value: 50 } }} />
          <OperationStatus state="failed" error="Amount must be at most 1000" onRetry={() => undefined} />
          <OperationStatus state="saved" />
          <StatusMessage tone="warning">{LONG}</StatusMessage>
          <Badge tone="success">Kept</Badge>
          <EmptyState title={LONG} message={LONG} />
          <LoadingState />
          <ErrorState message={LONG} onRetry={() => undefined} />
          <MetricCard label={LONG} value={null} unit="units" />
          <MetricCard label="Today" value={12.5} unit="units" hint="3 entries" />
          <TrendChart
            title={LONG}
            unit="units"
            points={daySeries("2026-09-25", 7, new Map([["2026-09-20", 4], ["2026-09-22", 0], ["2026-09-25", 9]]))}
            controls={<RangeSelect value={7} onChange={() => undefined} />}
          />
          <ReviewQueue
            items={ROWS}
            getId={(r) => r.id}
            getLabel={(r) => r.title}
            renderItem={(r) => <p>{r.title}</p>}
            decisions={[{ id: "kept", label: "Keep", doneLabel: "Kept" }]}
            onDecide={async () => undefined}
            reasonLabel="Reason"
          />
        </Section>
      </Columns>
    </Page>
  );
}

describe("accessibility of every kit component and state", () => {
  it.each(["populated", "empty", "loading", "failed"] as const)("%s state has no axe violations", async (state) => {
    const { container } = render(<Everything state={state} />);
    expect(await violations(container)).toEqual([]);
  });

  it("an open drawer is a labelled modal dialog with no violations", async () => {
    render(
      <DetailDrawer open onClose={() => undefined} title={LONG} footer={<Button>Save</Button>}>
        <TextField label="Title" />
      </DetailDrawer>,
    );
    const dialog = screen.getByRole("dialog", { name: LONG });
    expect(within(dialog).getByRole("button", { name: "Close" })).toBeInTheDocument();
    expect(await violations(document.body)).toEqual([]);
  });
});

describe("trend and metrics", () => {
  it("distinguishes missing days from recorded zeros and exposes the numbers", () => {
    const { container } = render(
      <TrendChart title="Daily amount" unit="units" points={daySeries("2026-09-25", 7, new Map([["2026-09-20", 4], ["2026-09-22", 0], ["2026-09-25", 9]]))} />,
    );
    expect(container.querySelectorAll(".a-trend__bar")).toHaveLength(2);
    expect(container.querySelectorAll(".a-trend__zero")).toHaveLength(1);
    expect(container.querySelectorAll(".a-trend__missing")).toHaveLength(4);
    const img = screen.getByRole("img");
    expect(img.getAttribute("aria-label")).toMatch(/7 days .* total 13 units; highest day 9 units; 4 days with no entry/);
    const table = screen.getByRole("table");
    expect(within(table).getAllByText("No entry")).toHaveLength(4);
    expect(within(table).getByText("0")).toBeInTheDocument();
  });

  it("shows No data rather than zero for a missing metric", () => {
    render(<MetricCard label="Average" value={null} unit="units" />);
    expect(screen.getByRole("group", { name: "Average" })).toHaveTextContent("No data");
  });
});
