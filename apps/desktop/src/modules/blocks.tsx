/**
 * The blocks a declarative screen is made of. Each one reads through a declared view and writes
 * through a declared action, so every module gets the same table, quick entry, metrics, trend,
 * board, list and form, drawn by the trusted shell.
 */
import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import type { DetailSpec, ScreenColumn, ActionBinding, AggregateResultPage, DeclaredView, FilterNode, RecordPageResult, RecordRow, ScreenBlock } from "../core/client";
import { MicButton, useSpeech } from "../shell/voice";
import { ActionForm } from "../workflows/ActionsView";
import { formatDay, formatNumber, humanize, outcomeWords, shiftDay, todayDay, useModule, useViewQuery, type ViewQueryBody } from "./useModule";

type Extract<K extends ScreenBlock["kind"]> = globalThis.Extract<ScreenBlock, { kind: K }>;

export function Block({ block, position = 0 }: { block: ScreenBlock; position?: number }) {
  switch (block.kind) {
    case "quick_entry":
      return <QuickEntry block={block} />;
    case "table":
      return <Table block={block} />;
    case "metrics":
      return <Metrics block={block} />;
    case "trend":
      return <Trend block={block} />;
    case "board":
      return <Board block={block} />;
    case "list":
      return <List block={block} />;
    case "form":
      return <Form block={block} folded={position > 0} />;
    case "text":
      return (
        <div className="card textblock">
          {block.title ? <h3>{block.title}</h3> : null}
          {block.body.split(/\n{2,}/).map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>
      );
  }
}

// ---------- helpers ----------

/** Saved lists may say `{"$today": -7}` for "seven days ago"; the shell fills the actual day. */
export function resolveDates(node: FilterNode): FilterNode {
  if ("all" in node) return { all: node.all.map(resolveDates) };
  if ("any" in node) return { any: node.any.map(resolveDates) };
  if ("not" in node) return { not: resolveDates(node.not) };
  const value = node.value as { $today?: number } | undefined;
  if (value && typeof value === "object" && typeof value.$today === "number") return { ...node, value: shiftDay(todayDay(), value.$today) };
  return node;
}

function fieldKind(view: DeclaredView | undefined, field: string): { kind: string; choices: string[] } {
  const { detail } = useModule();
  const collection = detail.collections.find((c) => c.name === view?.collection);
  const spec = collection?.fields.find((f) => f.name === field);
  return { kind: spec?.kind ?? "text", choices: spec?.choices ?? [] };
}

function cell(value: unknown, format: string | undefined, unit: string | null | undefined, kind: string): React.ReactNode {
  if (value === null || value === undefined || value === "") return <span className="faint">—</span>;
  const fmt = format ?? (kind === "number" || kind === "integer" ? "number" : kind === "date" ? "date" : kind === "datetime" ? "datetime" : kind === "boolean" ? "check" : kind === "choice" ? "pill" : "text");
  switch (fmt) {
    case "number":
      return typeof value === "number" ? formatNumber(value, unit) : String(value);
    case "date":
      return formatDay(String(value));
    case "datetime":
      return new Date(String(value)).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
    case "pill":
      return <span className="pill pill--gray">{humanize(String(value))}</span>;
    case "link":
      return (
        <a href={String(value)} target="_blank" rel="noreferrer">
          {String(value).replace(/^https?:\/\//, "").slice(0, 48)}
        </a>
      );
    case "check":
      return value ? "✓" : <span className="faint">—</span>;
    default:
      return String(value);
  }
}

function coerce(text: string, kind: string): unknown {
  if (kind === "number" || kind === "integer") {
    if (text.trim() === "") return null;
    const n = Number(text);
    return Number.isFinite(n) ? n : text;
  }
  if (kind === "boolean") return text === "true";
  return text === "" ? null : text;
}

function Status({ state }: { state: { ok: boolean; text: string } | null }) {
  if (!state) return null;
  return (
    <p className={state.ok ? "notice notice--ok" : "notice"} role={state.ok ? "status" : "alert"}>
      {state.text}
    </p>
  );
}

// ---------- quick entry ----------

function QuickEntry({ block }: { block: Extract<"quick_entry"> }) {
  const { run } = useModule();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  async function submit(e?: FormEvent) {
    e?.preventDefault();
    const value = text.trim();
    if (!value || busy) return;
    setBusy(true);
    setStatus(null);
    try {
      const outcome = await run(block.action, { ...block.extra, [block.input]: value });
      const words = outcomeWords(outcome, "Saved.");
      setStatus(words);
      if (words.ok) setText("");
    } catch (err) {
      setStatus({ ok: false, text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  }
  const typedBefore = useRef("");
  const speech = useSpeech((final, interim) => setText(`${typedBefore.current} ${final} ${interim}`.replace(/\s+/g, " ").trim()));
  function toggleMic() {
    if (!speech.listening) typedBefore.current = text;
    speech.toggle();
  }
  return (
    <form className="card quick-wrap" onSubmit={submit}>
      <div className="quick">
        <span aria-hidden="true" style={{ color: "var(--primary)", fontSize: 18 }}>
          +
        </span>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder={block.placeholder} aria-label={block.placeholder} disabled={busy} />
        {block.voice ? <MicButton listening={speech.listening} supported={speech.supported} onToggle={toggleMic} /> : null}
        <button type="submit" className="btn btn--primary" disabled={busy || !text.trim()}>
          {busy ? "Adding…" : "Add"}
        </button>
      </div>
      {status ? (
        <div className="quick__status">
          <Status state={status} />
        </div>
      ) : null}
    </form>
  );
}

// ---------- table ----------

function Table({ block }: { block: Extract<"table"> }) {
  const { view, run } = useModule();
  const spec = view(block.view);
  const [listId, setListId] = useState<string>(block.lists[0]?.id ?? "all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<{ field: string; direction: "asc" | "desc" } | null>(null);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [openId, setOpenId] = useState<string | null>(null);
  const collection = useModule().detail.collections.find((c) => c.name === spec?.collection);
  const kinds = useMemo(() => new Map((collection?.fields ?? []).map((f) => [f.name, f])), [collection]);
  const searchable = (spec?.filterable ?? []).filter((f) => kinds.get(f)?.kind === "text");
  // Quick filters: every choice column the view can filter on gets a dropdown, without the
  // module declaring anything (statuses and categories are what people narrow by).
  const facets = useMemo(
    () => block.columns.map((c) => c.field).filter((f) => (spec?.filterable ?? []).includes(f) && kinds.get(f)?.kind === "choice" && (kinds.get(f)?.choices ?? []).length > 0),
    [block.columns, spec?.filterable, kinds],
  );

  const body = useMemo<ViewQueryBody>(() => {
    const parts: FilterNode[] = [];
    const list = block.lists.find((l) => l.id === listId);
    if (list?.where) parts.push(resolveDates(list.where));
    const q = search.trim();
    if (q && searchable.length) parts.push({ any: searchable.map((f) => ({ field: f, op: "contains", value: q })) } as FilterNode);
    for (const [field, value] of Object.entries(picked)) if (value) parts.push({ field, op: "eq", value } as FilterNode);
    const where = parts.length === 0 ? undefined : parts.length === 1 ? parts[0] : ({ all: parts } as FilterNode);
    // Never ask for more than the view allows; Core refuses a page above its max_limit.
    const limit = Math.min(block.page_size, spec?.max_limit ?? block.page_size);
    return { where, order_by: sort ? [sort] : undefined, limit, cursor: cursors[cursors.length - 1] };
  }, [block.lists, block.page_size, listId, search, searchable, picked, sort, cursors, spec?.max_limit]);

  const { data, loading, error, reload } = useViewQuery<RecordPageResult>(spec ? block.view : null, body);
  const rows = data?.records ?? [];
  useEffect(() => {
    setCursors([null]);
  }, [listId, search, picked, sort]);
  const openRow = openId ? (rows.find((r) => r.id === openId) ?? null) : null;

  async function commit(row: RecordRow, field: string, text: string) {
    if (!block.edit?.id_param) return;
    const kind = kinds.get(field)?.kind ?? "text";
    const value = coerce(text, kind);
    if (value === (row.values[field] ?? null)) return;
    setStatus(null);
    try {
      const outcome = await run(block.edit.action, { ...block.edit.input, [block.edit.id_param]: row.id, [field]: value });
      const words = outcomeWords(outcome, "Saved.");
      if (!words.ok) setStatus(words);
    } catch (err) {
      setStatus({ ok: false, text: err instanceof Error ? err.message : String(err) });
    }
  }

  async function remove(row: RecordRow) {
    if (!block.delete?.id_param) return;
    const words = outcomeWords(await run(block.delete.action, { ...block.delete.input, [block.delete.id_param]: row.id }), "Removed.");
    setStatus(words.ok ? null : words);
  }

  async function rowAction(row: RecordRow, binding: ActionBinding) {
    const input = { ...binding.input, ...(binding.id_param ? { [binding.id_param]: row.id } : {}) };
    const words = outcomeWords(await run(binding.action, input), "Done.");
    setStatus(words.ok ? null : words);
  }

  const totals = block.totals.map((field) => ({
    field,
    value: rows.reduce((sum, r) => sum + (typeof r.values[field] === "number" ? (r.values[field] as number) : 0), 0),
  }));
  if (!spec) return <p className="notice">This screen refers to a view that is not declared.</p>;
  const hasActions = Boolean(block.delete || block.row_actions.length);
  return (
    <div className="card">
      {block.title ? (
        <div className="section__head" style={{ padding: "12px 12px 0", marginBottom: 0 }}>
          <h3>{block.title}</h3>
        </div>
      ) : null}
      <div className="toolbar">
        {block.lists.length ? (
          <select className="btn btn--sm" value={listId} onChange={(e) => setListId(e.target.value)} aria-label="Which entries">
            {block.lists.map((l) => (
              <option key={l.id} value={l.id}>
                {l.title}
              </option>
            ))}
            <option value="all">All</option>
          </select>
        ) : null}
        {searchable.length ? (
          <div className="search">
            <span aria-hidden="true">⌕</span>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search" aria-label="Search" />
          </div>
        ) : null}
        {facets.map((field) => (
          <select key={field} className="btn btn--sm" value={picked[field] ?? ""} onChange={(e) => setPicked((p) => ({ ...p, [field]: e.target.value }))} aria-label={`Filter by ${humanize(field).toLowerCase()}`}>
            <option value="">{humanize(field)}: any</option>
            {(kinds.get(field)?.choices ?? []).map((c) => (
              <option key={c} value={c}>
                {humanize(c)}
              </option>
            ))}
          </select>
        ))}
        <span className="toolbar__hint">{block.detail ? "Click a row to open it" : block.edit ? "Click a cell to edit" : ""}</span>
      </div>
      {error ? (
        <p className="notice" style={{ padding: 12 }} role="alert">
          {error}{" "}
          <button type="button" className="btn btn--sm" onClick={reload}>
            Try again
          </button>
        </p>
      ) : null}
      <div className="tablewrap">
        <table className="table">
          <thead>
            <tr>
              {block.columns.map((c) => {
                const kind = kinds.get(c.field)?.kind ?? "text";
                const numeric = kind === "number" || kind === "integer";
                const sortable = spec.sortable.includes(c.field);
                const title = c.title ?? humanize(c.field);
                return (
                  <th key={c.field} className={numeric ? "r" : undefined} aria-sort={sort?.field === c.field ? (sort.direction === "asc" ? "ascending" : "descending") : undefined}>
                    {sortable ? (
                      <button type="button" onClick={() => setSort((s) => (s?.field === c.field ? { field: c.field, direction: s.direction === "asc" ? "desc" : "asc" } : { field: c.field, direction: "asc" }))}>
                        {title}
                        {sort?.field === c.field ? (sort.direction === "asc" ? " ↑" : " ↓") : ""}
                      </button>
                    ) : (
                      title
                    )}
                  </th>
                );
              })}
              {hasActions ? <th aria-label="Actions" /> : null}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className={block.detail ? `row--open${openId === row.id ? " row--current" : ""}` : undefined} onClick={block.detail ? () => setOpenId(row.id) : undefined} aria-label={block.detail ? `Open ${String(row.values[block.detail.title_field ?? block.columns[0].field] ?? row.id)}` : undefined}>
                {block.columns.map((c) => (
                  <Cell key={c.field} row={row} column={c} kind={kinds.get(c.field)?.kind ?? "text"} choices={kinds.get(c.field)?.choices ?? []} editable={Boolean(block.edit) && c.editable} onCommit={(text) => commit(row, c.field, text)} />
                ))}
                {hasActions ? (
                  <td className="r">
                    {block.row_actions.map((b) => (
                      <button key={b.action + (b.title ?? "")} type="button" className="btn btn--sm rowbtn" onClick={() => rowAction(row, b)}>
                        {b.title ?? humanize(b.action)}
                      </button>
                    ))}
                    {block.delete ? (
                      <button type="button" className="btn btn--sm btn--ghost rowbtn" aria-label="Remove" title={block.delete.title ?? "Remove"} onClick={() => remove(row)}>
                        ✕
                      </button>
                    ) : null}
                  </td>
                ) : null}
              </tr>
            ))}
            {!loading && rows.length === 0 ? (
              <tr>
                <td colSpan={block.columns.length + (hasActions ? 1 : 0)} className="empty" style={{ whiteSpace: "normal" }}>
                  {block.empty ?? (search ? "Nothing matches." : "Nothing here yet.")}
                </td>
              </tr>
            ) : null}
          </tbody>
          {totals.length && rows.length ? (
            <tfoot>
              <tr>
                {block.columns.map((c, i) => {
                  const t = totals.find((x) => x.field === c.field);
                  return (
                    <td key={c.field} className={t ? "r num" : undefined}>
                      {t ? formatNumber(t.value, c.unit) : i === 0 ? (data?.next_cursor ? "This page" : "Total") : ""}
                    </td>
                  );
                })}
                {hasActions ? <td /> : null}
              </tr>
            </tfoot>
          ) : null}
        </table>
      </div>
      {block.detail && openRow ? (
        <Detail row={openRow} spec={block.detail} view={spec} columns={block.columns} kinds={kinds} onClose={() => setOpenId(null)} onAction={(binding) => rowAction(openRow, binding)} onRemove={block.delete ? () => remove(openRow) : undefined} />
      ) : null}
      <div className="pager">
        <span>{loading ? "Loading…" : `${rows.length} shown`}</span>
        <Status state={status} />
        <span className="spacer" />
        <button type="button" className="btn btn--sm" disabled={cursors.length <= 1} onClick={() => setCursors((c) => c.slice(0, -1))}>
          Previous
        </button>
        <button type="button" className="btn btn--sm" disabled={!data?.next_cursor} onClick={() => setCursors((c) => [...c, data?.next_cursor ?? null])}>
          Next
        </button>
      </div>
    </div>
  );
}

/** A record's own page: every field readable, long text as paragraphs, and the actions that
 *  apply to it. Opened from a table row; a panel inside the same card, not a new screen. */
function Detail({
  row,
  spec,
  view,
  columns,
  kinds,
  onClose,
  onAction,
  onRemove,
}: {
  row: RecordRow;
  spec: DetailSpec;
  view: DeclaredView;
  columns: ScreenColumn[];
  kinds: Map<string, { kind: string; choices?: string[] | null }>;
  onClose: () => void;
  onAction: (binding: ActionBinding) => void;
  onRemove?: () => void;
}) {
  const titleField = spec.title_field ?? columns[0]?.field;
  const title = titleField ? String(row.values[titleField] ?? "") : "";
  const long = new Set(spec.long_fields);
  const all = spec.fields.length ? spec.fields : (view.fields?.length ? view.fields : [...kinds.keys()]);
  const shown = all.filter((f) => f !== titleField && !long.has(f));
  const format = (field: string) => columns.find((c) => c.field === field)?.format ?? (/link|url/.test(field) && typeof row.values[field] === "string" && /^https?:\/\//.test(String(row.values[field])) ? "link" : undefined);
  const unit = (field: string) => columns.find((c) => c.field === field)?.unit;
  const when = (iso: string) => (iso ? new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "");
  return (
    <section className="drawer" aria-label={title || "Details"}>
      <div className="drawer__head">
        <h3>{title || "Details"}</h3>
        <span className="spacer" />
        {spec.actions.map((b) => (
          <button key={b.action + (b.title ?? "")} type="button" className="btn btn--sm" onClick={() => onAction(b)}>
            {b.title ?? humanize(b.action)}
          </button>
        ))}
        {onRemove ? (
          <button type="button" className="btn btn--sm btn--danger" onClick={onRemove}>
            Remove
          </button>
        ) : null}
        <button type="button" className="btn btn--sm btn--ghost" onClick={onClose} aria-label="Close details">
          ✕
        </button>
      </div>
      <dl className="kv">
        {shown.map((field) => (
          <div key={field} className="kv__row">
            <dt>{humanize(field)}</dt>
            <dd>{cell(row.values[field], format(field), unit(field), kinds.get(field)?.kind ?? "text")}</dd>
          </div>
        ))}
        {row.created_at ? (
          <div className="kv__row">
            <dt>Added</dt>
            <dd>{when(row.created_at)}</dd>
          </div>
        ) : null}
        {row.updated_at && row.updated_at !== row.created_at ? (
          <div className="kv__row">
            <dt>Last changed</dt>
            <dd>{when(row.updated_at)}</dd>
          </div>
        ) : null}
      </dl>
      {spec.long_fields.map((field) => (
        <div key={field} className="drawer__long">
          <h4>{humanize(field)}</h4>
          {row.values[field] ? <p>{String(row.values[field])}</p> : <p className="faint">Nothing yet.</p>}
        </div>
      ))}
    </section>
  );
}

function Cell({
  row,
  column,
  kind,
  choices,
  editable,
  onCommit,
}: {
  row: RecordRow;
  column: Extract<"table">["columns"][number];
  kind: string;
  choices: string[];
  editable: boolean;
  onCommit: (text: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const value = row.values[column.field];
  const numeric = kind === "number" || kind === "integer";
  const estimate = row.provenance?.[column.field]?.source === "model_estimate";
  function begin(e?: { stopPropagation: () => void }) {
    if (!editable) return;
    e?.stopPropagation(); // editing a cell must not also open or close the row's page
    setText(value === null || value === undefined ? "" : String(value));
    setEditing(true);
  }
  function finish(commit: boolean) {
    setEditing(false);
    if (commit) onCommit(text);
  }
  function key(e: KeyboardEvent) {
    if (e.key === "Enter") finish(true);
    if (e.key === "Escape") finish(false);
  }
  if (editing) {
    return (
      <td className={numeric ? "r" : undefined} onClick={(e) => e.stopPropagation()}>
        {kind === "choice" ? (
          <select autoFocus value={text} onChange={(e) => setText(e.target.value)} onBlur={() => finish(true)} onKeyDown={key} aria-label={column.title ?? humanize(column.field)}>
            <option value="">—</option>
            {choices.map((c) => (
              <option key={c} value={c}>
                {humanize(c)}
              </option>
            ))}
          </select>
        ) : (
          <input
            autoFocus
            type={numeric ? "number" : kind === "date" ? "date" : "text"}
            step={kind === "number" ? "any" : undefined}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onFocus={(e) => e.currentTarget.select()}
            onBlur={() => finish(true)}
            onKeyDown={key}
            aria-label={column.title ?? humanize(column.field)}
          />
        )}
      </td>
    );
  }
  return (
    <td className={`${numeric ? "r num" : ""} ${editable ? "editable" : ""}`.trim()} onClick={(e) => begin(e)} tabIndex={editable ? 0 : undefined} onKeyDown={(e) => e.key === "Enter" && begin(e)} title={editable ? "Click to edit" : undefined}>
      {cell(value, column.format ?? undefined, column.unit, kind)}
      {estimate ? (
        <span className="est" title="An estimate. Click the cell to correct it." aria-label="estimate">
          ≈
        </span>
      ) : null}
    </td>
  );
}

// ---------- metrics ----------

function pickGroup(page: AggregateResultPage | null, view: DeclaredView | undefined): Record<string, number | string | null> | null | undefined {
  if (!page) return undefined;
  const dayKey = view?.group_by.find((g) => g.bucket === "day");
  if (dayKey) {
    const key = `${dayKey.field}_day`;
    const today = todayDay();
    const group = page.groups.find((g) => g.key[key] === today);
    return group ? group.values : null;
  }
  return page.groups[0]?.values ?? null;
}

function Metrics({ block }: { block: Extract<"metrics"> }) {
  return (
    <div>
      {block.title ? (
        <div className="section__head">
          <h2 style={{ fontSize: 18 }}>{block.title}</h2>
        </div>
      ) : null}
      <div className="metrics">
        {block.cards.map((card) => (
          <Metric key={card.title} card={card} />
        ))}
      </div>
    </div>
  );
}

/** A goal that lives in a record the person set (goal_from), or a fixed number (goal). */
function useGoal(goal: number | null | undefined, from: { view: string; field: string } | null | undefined): number | null {
  const body = useMemo<ViewQueryBody>(() => ({ limit: 1 }), []);
  const { data } = useViewQuery<RecordPageResult>(from ? from.view : null, body);
  if (from) {
    const v = data?.records[0]?.values[from.field];
    return typeof v === "number" ? v : null;
  }
  return goal ?? null;
}

function Metric({ card }: { card: Extract<"metrics">["cards"][number] }) {
  const { view } = useModule();
  const spec = view(card.view);
  const body = useMemo<ViewQueryBody>(() => ({}), []);
  const { data, error } = useViewQuery<AggregateResultPage>(spec ? card.view : null, body);
  const goal = useGoal(card.goal, card.goal_from);
  const values = pickGroup(data, spec);
  const raw = values ? values[card.metric] : null;
  const value = typeof raw === "number" ? raw : null;
  const dayBased = Boolean(spec?.group_by.some((g) => g.bucket === "day"));
  return (
    <div className="card metric">
      <div className="metric__lab">{card.title}</div>
      <div className="metric__big num">
        {error ? <span className="notice">Couldn't load</span> : values === undefined ? "…" : value === null ? <small>{dayBased ? "Nothing today" : "No data"}</small> : formatNumber(value, card.unit)}
        {goal != null && value !== null ? <small> of {formatNumber(goal)}</small> : null}
      </div>
      {goal != null && value !== null ? (
        <>
          <div className="goalbar">
            <i className={value > goal ? "over" : undefined} style={{ width: `${Math.min(100, (value / goal) * 100)}%` }} />
          </div>
          <div className="faint">
            {value <= goal ? `${formatNumber(goal - value, card.unit)} left` : `${formatNumber(value - goal, card.unit)} over`}
            {card.goal_label ? ` · ${card.goal_label}` : ""}
          </div>
        </>
      ) : card.hint ? (
        <div className="faint">{card.hint}</div>
      ) : null}
    </div>
  );
}

// ---------- trend ----------

/** The rendered width of an element, so a chart's coordinate space matches its pixels. */
function useWidth<T extends HTMLElement>(fallback: number): [React.RefObject<T | null>, number] {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const next = Math.round(entries[0]?.contentRect.width ?? fallback);
      if (next > 0) setWidth(next);
    });
    observer.observe(node);
    setWidth(Math.round(node.getBoundingClientRect().width) || fallback);
    return () => observer.disconnect();
  }, [fallback]);
  return [ref, width];
}

function Trend({ block }: { block: Extract<"trend"> }) {
  const { view } = useModule();
  const spec = view(block.view);
  const [box, width] = useWidth<HTMLDivElement>(420);
  const body = useMemo<ViewQueryBody>(() => ({}), []);
  const { data, error } = useViewQuery<AggregateResultPage>(spec ? block.view : null, body);
  const goal = useGoal(block.goal, block.goal_from);
  const today = todayDay();
  const days: string[] = [];
  for (let i = block.days - 1; i >= 0; i--) days.push(shiftDay(today, -i));
  const byDay = new Map<string, number>();
  for (const g of data?.groups ?? []) {
    const key = String(g.key[block.x] ?? "");
    const v = g.values[block.y];
    if (typeof v === "number") byDay.set(key, v);
  }
  const present = days.filter((d) => byDay.has(d));
  const values = present.map((d) => byDay.get(d) as number);
  const avg = values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
  const W = Math.max(280, width), H = 150, L = 44, R = 10, T = 10, B = 22;
  const all = [...values, ...(goal != null ? [goal] : [])];
  const max = all.length ? Math.max(...all) * 1.1 : 1;
  const min = 0;
  const x = (i: number) => L + (i * (W - L - R)) / Math.max(1, days.length - 1);
  const y = (v: number) => T + (H - T - B) * (1 - (v - min) / (max - min || 1));
  const segments: string[] = [];
  let current: string[] = [];
  days.forEach((d, i) => {
    const v = byDay.get(d);
    if (v === undefined) {
      if (current.length) segments.push(current.join(" "));
      current = [];
    } else current.push(`${current.length ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`);
  });
  if (current.length) segments.push(current.join(" "));
  return (
    <div className="card trend">
      <div className="trend__head">
        <span className="metric__lab">{block.title}</span>
        <span className="faint">
          {values.length ? `${values.length} of ${days.length} days · average ${formatNumber(avg ?? 0, block.unit)}` : `No entries in the last ${days.length} days`}
          {goal != null ? ` · goal ${formatNumber(goal, block.unit)}` : ""}
        </span>
      </div>
      {error ? <p className="notice">{error}</p> : null}
      <div ref={box} className="chart__box">
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={`${block.title}, last ${days.length} days`}>
        {[0, 0.5, 1].map((k) => {
          const v = min + (max - min) * k;
          return (
            <g key={k}>
              <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="var(--line)" />
              <text x={L - 6} y={y(v) + 3} textAnchor="end">
                {formatNumber(Math.round(v))}
              </text>
            </g>
          );
        })}
        {goal != null ? (
          <>
            <line x1={L} x2={W - R} y1={y(goal)} y2={y(goal)} stroke="var(--chart-2)" strokeDasharray="4 3" />
            <text x={W - R} y={y(goal) - 4} textAnchor="end" fill="var(--chart-2)">
              goal
            </text>
          </>
        ) : null}
        {segments.map((d, i) => (
          <path key={i} d={d} fill="none" stroke="var(--chart)" strokeWidth="2" />
        ))}
        {days.map((d, i) => {
          const v = byDay.get(d);
          return v === undefined ? null : <circle key={d} cx={x(i)} cy={y(v)} r={2.5} fill="var(--chart)" />;
        })}
        <text x={x(0)} y={H - 8}>
          {formatDay(days[0])}
        </text>
        <text x={x(days.length - 1)} y={H - 8} textAnchor="end">
          today
        </text>
      </svg>
      </div>
    </div>
  );
}

// ---------- board ----------

/** Subtitle values shown the way their field kind reads: days as dates, numbers with grouping. */
function subtitle(row: RecordRow, fields: string[], kinds: Map<string, { kind: string }>): string {
  return fields
    .map((f) => {
      const v = row.values[f];
      if (v === null || v === undefined || v === "") return null;
      const kind = kinds.get(f)?.kind ?? "text";
      if (kind === "date") return formatDay(String(v));
      if (typeof v === "number") return formatNumber(v);
      if (kind === "choice") return humanize(String(v));
      return String(v);
    })
    .filter((v): v is string => v !== null)
    .join(" · ");
}

function useKinds(view: DeclaredView | undefined): Map<string, { kind: string; choices?: string[] | null }> {
  const { detail } = useModule();
  const collection = detail.collections.find((c) => c.name === view?.collection);
  return useMemo(() => new Map((collection?.fields ?? []).map((f) => [f.name, f])), [collection]);
}

function Board({ block }: { block: Extract<"board"> }) {
  const { view, run } = useModule();
  const spec = view(block.view);
  const kinds = useKinds(spec);
  const body = useMemo<ViewQueryBody>(() => ({ limit: Math.min(200, spec?.max_limit ?? 200) }), [spec?.max_limit]);
  const { data, error } = useViewQuery<RecordPageResult>(spec ? block.view : null, body);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const rows = data?.records ?? [];
  const badge = block.badge_field ? fieldKind(spec, block.badge_field) : null;
  async function move(row: RecordRow, to: string) {
    if (!block.move?.id_param || !block.field_param) return;
    const words = outcomeWords(await run(block.move.action, { ...block.move.input, [block.move.id_param]: row.id, [block.field_param]: to }), "Moved.");
    setStatus(words.ok ? null : words);
  }
  async function act(row: RecordRow, binding: ActionBinding) {
    const words = outcomeWords(await run(binding.action, { ...binding.input, ...(binding.id_param ? { [binding.id_param]: row.id } : {}) }), "Done.");
    setStatus(words.ok ? null : words);
  }
  return (
    <div>
      {block.title ? (
        <div className="section__head">
          <h2 style={{ fontSize: 18 }}>{block.title}</h2>
        </div>
      ) : null}
      {error ? <p className="notice">{error}</p> : null}
      <Status state={status} />
      <div className="board">
        {block.columns.map((col) => {
          const cards = rows.filter((r) => r.values[block.group_field] === col);
          return (
            <div className="board__col" key={col}>
              <h4>
                {humanize(col)} <span>{cards.length}</span>
              </h4>
              {cards.map((row) => (
                <div className="card jcard" key={row.id}>
                  <b>{String(row.values[block.title_field] ?? "")}</b>
                  {block.subtitle_fields.length ? <div className="jcard__sub">{subtitle(row, block.subtitle_fields, kinds)}</div> : null}
                  {block.badge_field && row.values[block.badge_field] != null ? (
                    <div className="jcard__meta">
                      <span className="pill pill--info">{cell(row.values[block.badge_field], undefined, null, badge?.kind ?? "text")}</span>
                    </div>
                  ) : null}
                  <div className="row" style={{ gap: 6 }}>
                    {block.move ? (
                      <select value={col} onChange={(e) => move(row, e.target.value)} aria-label="Move to">
                        {block.columns.map((c) => (
                          <option key={c} value={c}>
                            {humanize(c)}
                          </option>
                        ))}
                      </select>
                    ) : null}
                    {block.card_actions.map((b) => (
                      <button key={b.action + (b.title ?? "")} type="button" className="btn btn--sm" onClick={() => act(row, b)}>
                        {b.title ?? humanize(b.action)}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
              {!cards.length ? <p className="faint">None</p> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------- list ----------

function List({ block }: { block: Extract<"list"> }) {
  const { view, run } = useModule();
  const spec = view(block.view);
  const kinds = useKinds(spec);
  const body = useMemo<ViewQueryBody>(() => ({ limit: Math.min(100, spec?.max_limit ?? 100) }), [spec?.max_limit]);
  const { data, error, loading } = useViewQuery<RecordPageResult>(spec ? block.view : null, body);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const rows = data?.records ?? [];
  const badge = block.badge_field ? fieldKind(spec, block.badge_field) : null;
  async function act(row: RecordRow, binding: ActionBinding) {
    const words = outcomeWords(await run(binding.action, { ...binding.input, ...(binding.id_param ? { [binding.id_param]: row.id } : {}) }), "Done.");
    setStatus(words.ok ? null : words);
  }
  return (
    <div>
      {block.title ? (
        <div className="section__head">
          <h2 style={{ fontSize: 18 }}>{block.title}</h2>
        </div>
      ) : null}
      {error ? <p className="notice">{error}</p> : null}
      <Status state={status} />
      <div className="card list">
        {rows.map((row) => (
          <div className="item" key={row.id}>
            <div className="item__body">
              <b>
                {block.link_field && row.values[block.link_field] ? (
                  <a href={String(row.values[block.link_field])} target="_blank" rel="noreferrer">
                    {String(row.values[block.title_field] ?? "")}
                  </a>
                ) : (
                  String(row.values[block.title_field] ?? "")
                )}
              </b>
              {block.subtitle_fields.length ? <div className="item__sub">{subtitle(row, block.subtitle_fields, kinds)}</div> : null}
            </div>
            {block.badge_field && row.values[block.badge_field] != null ? <span className="pill pill--gray">{cell(row.values[block.badge_field], undefined, null, badge?.kind ?? "text")}</span> : null}
            {block.item_actions.map((b) => (
              <button key={b.action + (b.title ?? "")} type="button" className="btn btn--sm" onClick={() => act(row, b)}>
                {b.title ?? humanize(b.action)}
              </button>
            ))}
          </div>
        ))}
        {!loading && !rows.length ? <p className="empty">{block.empty ?? "Nothing here yet."}</p> : null}
      </div>
    </div>
  );
}

// ---------- form ----------

function Form({ block, folded = false }: { block: Extract<"form">; folded?: boolean }) {
  const { client, detail, action, changed, view } = useModule();
  const [open, setOpen] = useState(!folded);
  const spec = action(block.action);
  const prefillView = block.prefill_view ? view(block.prefill_view) : undefined;
  const body = useMemo<ViewQueryBody>(() => ({ limit: 1 }), []);
  const { data, loading } = useViewQuery<RecordPageResult>(prefillView ? block.prefill_view ?? null : null, body);
  if (!spec) return <p className="notice">This screen refers to an action that is not declared.</p>;
  if (block.prefill_view && loading && !data) return <p className="faint">Loading…</p>;
  const first = data?.records[0];
  const initial: Record<string, string | boolean> = {};
  if (first) for (const [k, v] of Object.entries(first.values)) initial[k] = typeof v === "boolean" ? v : v === null || v === undefined ? "" : String(v);
  const form = <ActionForm key={first?.id ?? "new"} client={client} appId={detail.app_id} action={spec} onChanged={changed} initial={initial} title={block.title ?? undefined} description={block.description ?? null} submitLabel={block.submit_label ?? undefined} />;
  if (!folded) return form;
  const title = block.title ?? spec.title;
  return (
    <section className="folded" aria-label={title}>
      <div className="folded__bar">
        <h3>{title}</h3>
        {block.description ? <span className="faint">{block.description}</span> : null}
        <span className="spacer" />
        <button type="button" className="btn btn--sm" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? "Close" : `Open`}
        </button>
      </div>
      {open ? form : null}
    </section>
  );
}
