# @alpha/ui-kit reference (for generated App UI)

This sheet ships inside the pinned UI build profile. Generated UI imports only `react`,
`react-dom`, `@alpha/ui-kit` and its own files. It runs in a sandboxed frame with no network;
everything it reads or changes goes through the App's declared **views** and **actions**.

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@alpha/ui-kit/styles.css";
import { AlphaApp, Page } from "@alpha/ui-kit";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AlphaApp>
      <Page title="…">…</Page>
    </AlphaApp>
  </StrictMode>,
);
```

The screen is type-checked with TypeScript (strict) against this kit's types before it is built.
Give every required prop (for example `RecordTable` needs `caption`, `columns`, `rows` and
`getRowId`); a type error fails the build with the exact line.

`AlphaApp` connects to Alpha and shows the connecting, failed and closed-session states for you.
Do not write a bundler config, `package.json`, `fetch` calls or inline `style` attributes; the
CSP blocks them.

**Use `Form`, never `<form>`.** The frame is sandboxed without form submission, so a native
`<form onSubmit>` silently never fires. `Form` submits on Enter in single-line fields and when a
`<Button type="submit">` inside it is activated; Enter in a text area still adds a new line.

## Choose the interaction first

| The person mostly… | Use | Not |
|---|---|---|
| adds small things often | `QuickEntry` at the top, with a `parse` that previews what will be saved | a long form |
| compares, filters, drills into many items | `FilterBar` + `RecordTable` + `Pager`, `DetailDrawer` to inspect and correct | a column dump |
| decides on incoming items | `ReviewQueue` with named decisions and a reason | a table of checkboxes |
| wants to know how things change | `MetricCard`s and `TrendChart` over a `RangeSelect` | a table of numbers only |
| supplies inputs or confirms something | fields inside a `Form` with `OperationStatus` | auto-generated forms |

Tables are one option, not the default. Write custom React when no pattern fits; keep kit tokens
and classes so it looks and behaves like the rest.

**Lay the screen out around that choice.** Alpha shows an App's screen in about 1000 × 480 px in
its default window (670 px wide at the smallest). The render check requires the main
interaction's first control to be visible there without scrolling, and a second entry straight
after the first to be saved.
1. Put the main interaction at the top.
2. Put the working list or today's summary right after it.
3. Keep secondary forms (corrections, settings, rare actions) in a `DetailDrawer` or a
   collapsed `<details>`, not stacked above the list.
4. Mark required fields `required`: `Form` stops an empty submission, says which fields are
   missing and focuses the first. After a save that clears the fields, focus returns to the
   first one.

## Data: views, actions and outcomes

- `useView(viewId, { where, order_by, limit })` → `{ records, loading, error, refresh, next, previous, hasNext, hasPrevious, page }`.
  A view is declared in `app.yaml` under `ui.views`; the UI may filter only on its `filterable`
  fields, sort only on its `sortable` fields and page within `max_limit`.
- `useAggregate(viewId, where)` → `{ groups: [{ key, values }], loading, error }` for an
  aggregate view (grouping and metrics are fixed by the view; day buckets come back as
  `<field>_day`).
- `useAction(actionId)` → `{ run(input), state, error, output, reset }`. `run` resolves only when
  the platform reports the action **succeeded** and rejects with an `ActionFailed` otherwise. Views
  refresh automatically after a success, so the screen shows committed values and revisions.
- Filters: `eq, ne, lt, lte, gt, gte, oneOf, contains, startsWith, isEmpty, not, allOf, anyOf`;
  sorting: `orderBy("-noted_on", "title")`. `allOf` ignores `undefined`, which keeps optional
  filters simple.
- Records arrive as `{ id, revision, values, provenance, created_at, updated_at }`. Send the
  `revision` you showed as `expected_revision` when changing a record; a stale revision fails
  instead of overwriting someone else's change.

## Saving: never show a failed save as stored

```tsx
const save = useAction("update_entry");
<Form onSubmit={async () => {
  try { await save.run({ id: row.id, expected_revision: row.revision, changes }); close(); }
  catch { /* OperationStatus explains; keep the draft so it can be fixed and saved again */ }
}}>
  …fields…
  <Button type="submit" variant="primary" busy={save.state === "saving"} busyLabel="Saving…">Save</Button>
  <OperationStatus state={save.state} error={save.error} />
</Form>
```

Keep the person's input after a failure, keep focus where they were, and let Enter retry.
`friendlyError` already turns platform messages into plain language.

## Components

| Component | Key props | Keyboard and accessibility |
|---|---|---|
| `Page` | `title`, `description`, `actions`, `status` | one `h1`, main landmark |
| `Section` | `title`, `description`, `actions` | titled region (`h2`) |
| `Stack`, `Cluster`, `Columns` | layout only | `Columns` stacks on narrow windows |
| `Button` | `variant` primary/secondary/danger/ghost, `busy`, `busyLabel`, `small` | real `<button>`; busy = disabled + `aria-busy` |
| `TextField`, `NumberField`, `DateField`, `SelectField`, `TextAreaField`, `CheckboxField` | `label`, `hint`, `error`, `required` | label, hint and error are wired with ids; errors are announced |
| `Field` | render function receiving `{ id, aria-describedby, aria-invalid }` | for custom controls |
| `Form` | `onSubmit`, `label` | Enter in a single-line field or a submit `Button` submits; works in the sandbox |
| `parseNumber(text)` | → `{ ok, value }` or `{ ok: false, message }` | keeps what the person typed |
| `QuickEntry` | `label`, `parse(text) → ParseResult`, `onSubmit(value) → { undo? }` | Enter submits, focus stays, Escape clears, failures keep the text |
| `FilterBar` | `filters`, `values`, `onChange`, `resultLabel` | search box + selects, "Clear filters", result count announced |
| `RecordTable` | required `caption`, `columns`, `rows`, `getRowId`; optional `getRowLabel`, `onOpen`, `sort`, `onSortChange`, `selectedIds`, `loading`, `error`, `onRetry`, `empty`, `footer` | first column opens the row; sortable headings are buttons with `aria-sort`; rows become labelled cards under 640px |
| `Pager` | `label`, `hasPrevious`, `hasNext`, `onPrevious`, `onNext` | labelled navigation |
| `DetailDrawer` | `open`, `onClose`, `title`, `description`, `footer` | native modal dialog: focus moves in, Escape closes, focus returns |
| `DetailList` | `items: [{ label, value }]` | definition list |
| `ReviewQueue` | `items`, `decisions`, `decisionOf`, `onDecide`, `reasonLabel`, `bulk` | ← → move, 1–n decide (card focused); bulk needs a second confirmation; decisions stay visible |
| `MetricCard` | `label`, `value` (`null` = "No data"), `unit`, `hint` | grouped and labelled |
| `TrendChart` | `title`, `points` from `daySeries`, `unit`, `controls` | missing days are dashed gaps, zero is a baseline mark; numbers available as a table |
| `RangeSelect` | `value`, `onChange`, `options` | labelled select |
| `StatusMessage`, `Badge` | `tone` info/success/warning/danger | icon + text; never color alone |
| `EmptyState`, `LoadingState`, `ErrorState`, `OperationStatus` | titles, messages, `onRetry` | status/alert roles |
| `ProvenanceNote` | `provenance` from a record field | labels model estimates and the person's corrections |

Formatting: `formatNumber`, `formatWithUnit`, `formatDay`, `today`, `addDays`, `daySeries`.

## Quality bar for every generated screen

- Empty, loading, saving, validation error, failure and narrow-window states all exist and say
  what to do next. Missing data is shown as missing, never as zero.
- Model estimates are labelled (`ProvenanceNote`) and easy to correct.
- Everything works with the keyboard alone; every control has a visible label; focus is visible.
- No horizontal scrolling at 768 px; long titles wrap.
- A failed save keeps what was typed (required by the render check); clear fields only after a
  save succeeded.
- Averages over time count only periods with entries and say how many there were; `TrendChart`
  shows "Days with entries: n of m".
- Words are the person's words: no field ids, collection names, JSON or error codes on screen.

## Testing a composition without Alpha

`@alpha/ui-kit/testing` exports `createMemoryApp({ collections, views, actions })`, an in-memory
App behind the real bridge protocol, and `failNext(actionId, message)` to rehearse failures.
Wrap the screen in `<AlphaProvider client={memory.client}>`.
