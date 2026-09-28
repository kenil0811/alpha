/**
 * A collection's derived page: Alpha draws it for every table a module keeps, so nothing has
 * to be designed. The table comes first with the person's own edits in place; the other views
 * (board, list, calendar, chart) are a click away; a saved list is a filter plus the columns
 * shown. Changes made here are the person's own records, not a module action.
 */
import { type DragEvent, type FormEvent, type KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type CollectionSummary, type FilterNode, type RecordRow, isConnectionsClient } from "../core/client";
import { DATE_KINDS, coerce, editText, firstOfKind, inputType, isNumeric, openChoices, showValue, titleFieldOf, type FieldInfo } from "./fields";
import { Block } from "./blocks";
import { formatNumber, humanize, useModule } from "./useModule";

export type PageView = "table" | "board" | "list" | "calendar" | "chart";
const VIEWS: { id: PageView; label: string }[] = [
  { id: "table", label: "Table" },
  { id: "board", label: "Board" },
  { id: "list", label: "List" },
  { id: "calendar", label: "Calendar" },
  { id: "chart", label: "Chart" },
];
const PAGE = 100;

interface SavedList {
  id: string;
  title: string;
  filters: Record<string, string>;
  search: string;
  hideDone: boolean;
  hidden: string[];
}

function remembered<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}
function remember(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* a page without storage forgets its layout, nothing more */
  }
}

export function DataPage({ collection }: { collection: CollectionSummary }) {
  const { client, detail, version, changed } = useModule();
  const appId = detail.app_id;
  const fields = collection.fields as FieldInfo[];
  const byName = useMemo(() => new Map(fields.map((f) => [f.name, f])), [fields]);
  const page = collection.page ?? null;
  const key = `alpha.page.${appId}.${collection.name}`;
  const titleField = titleFieldOf(fields, collection.title_field);
  const statusField = useMemo(() => fields.find((f) => f.kind === "status"), [fields]);
  const groupField = useMemo(() => (page?.group_field ? byName.get(page.group_field) : undefined) ?? statusField ?? firstOfKind(fields, new Set(["choice"])), [page?.group_field, byName, statusField, fields]);
  const dateField = useMemo(() => (page?.date_field ? byName.get(page.date_field) : undefined) ?? firstOfKind(fields, DATE_KINDS), [page?.date_field, byName, fields]);
  const numericField = useMemo(() => firstOfKind(fields, new Set(["number", "integer"])), [fields]);

  const [view, setView] = useState<PageView>(() => remembered<PageView>(`${key}.view`, page?.view ?? "table"));
  const [lists, setLists] = useState<SavedList[]>(() => remembered<SavedList[]>(`${key}.lists`, []));
  const [listId, setListId] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [hideDone, setHideDone] = useState(false);
  const [sort, setSort] = useState<{ field: string; direction: "asc" | "desc" } | null>(page?.sort ?? null);
  // Columns the person hid are remembered; a field the module gains later shows up on its own.
  const [hidden, setHidden] = useState<string[]>(() => remembered<string[]>(`${key}.hidden`, []));
  // The order the person put columns in, and the widths they dragged; new fields go to the end.
  const [order, setOrder] = useState<string[]>(() => remembered<string[]>(`${key}.order`, []));
  const [widths, setWidths] = useState<Record<string, number>>(() => remembered<Record<string, number>>(`${key}.widths`, {}));
  const columns = useMemo(() => {
    const base = (page?.columns ?? fields.map((f) => f.name)).filter((c) => !hidden.includes(c));
    const placed = order.filter((c) => base.includes(c));
    return [...placed, ...base.filter((c) => !placed.includes(c))];
  }, [page?.columns, fields, hidden, order]);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [rows, setRows] = useState<RecordRow[] | null>(null);
  const [next, setNext] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [menu, setMenu] = useState(false);
  const [month, setMonth] = useState(() => {
    const now = new Date();
    return { y: now.getFullYear(), m: now.getMonth() };
  });

  useEffect(() => remember(`${key}.view`, view), [key, view]);
  useEffect(() => remember(`${key}.hidden`, hidden), [key, hidden]);
  useEffect(() => remember(`${key}.order`, order), [key, order]);
  useEffect(() => remember(`${key}.widths`, widths), [key, widths]);
  const moveColumn = (name: string, by: -1 | 1) =>
    setOrder(() => {
      const current = [...columns];
      const at = current.indexOf(name);
      const to = at + by;
      if (at < 0 || to < 0 || to >= current.length) return current;
      current.splice(at, 1);
      current.splice(to, 0, name);
      return current;
    });
  useEffect(() => remember(`${key}.lists`, lists), [key, lists]);

  const searchable = useMemo(() => fields.filter((f) => f.kind === "text" || f.kind === "long_text" || f.kind === "url").map((f) => f.name), [fields]);
  const facets = useMemo(() => fields.filter((f) => (f.kind === "choice" || f.kind === "status") && (f.choices ?? []).length > 0), [fields]);

  const where = useMemo<FilterNode | undefined>(() => {
    const parts: FilterNode[] = [];
    const q = search.trim();
    if (q && searchable.length) parts.push({ any: searchable.map((f) => ({ field: f, op: "contains", value: q })) } as FilterNode);
    for (const [field, value] of Object.entries(filters)) if (value) parts.push({ field, op: "eq", value } as FilterNode);
    if (hideDone && statusField) parts.push({ field: statusField.name, op: "in", value: openChoices(statusField) } as FilterNode);
    return parts.length === 0 ? undefined : parts.length === 1 ? parts[0] : ({ all: parts } as FilterNode);
  }, [search, searchable, filters, hideDone, statusField]);

  const load = useCallback(() => {
    if (!client.queryRecordsPage) return;
    const order = sort ? [sort] : [{ field: "created_at", direction: "desc" as const }];
    client
      .queryRecordsPage(appId, { collection: collection.name, where, order_by: order, limit: PAGE, cursor: cursors[cursors.length - 1] })
      .then((result) => {
        setRows(result.records);
        setNext(result.next_cursor);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [client, appId, collection.name, where, sort, cursors]);
  useEffect(load, [load, version]);
  useEffect(() => setCursors([null]), [where, sort]);

  async function mutate(mutation: Record<string, unknown>, words: string): Promise<boolean> {
    if (!client.mutateRecord) return false;
    setStatus(null);
    try {
      await client.mutateRecord(appId, mutation);
      load();
      changed();
      return true;
    } catch (e) {
      setStatus({ ok: false, text: `${words}: ${e instanceof Error ? e.message : String(e)}` });
      return false;
    }
  }
  function commit(row: RecordRow, field: FieldInfo, text: string) {
    const value = coerce(text, field.kind);
    const current = row.values[field.name] ?? null;
    if (JSON.stringify(value) === JSON.stringify(current)) return;
    void mutate({ op: "correct", collection: collection.name, id: row.id, expected_revision: row.revision, changes: { [field.name]: value } }, "Could not save the change");
  }
  function remove(row: RecordRow) {
    setOpenId(null);
    void mutate({ op: "delete", collection: collection.name, id: row.id, expected_revision: row.revision }, "Could not remove it");
  }
  function move(row: RecordRow, field: FieldInfo, value: string) {
    if ((row.values[field.name] ?? null) === value) return;
    void mutate({ op: "correct", collection: collection.name, id: row.id, expected_revision: row.revision, changes: { [field.name]: value } }, "Could not move it");
  }

  function applyList(id: string) {
    setListId(id);
    const list = lists.find((l) => l.id === id);
    setFilters(list?.filters ?? {});
    setSearch(list?.search ?? "");
    setHideDone(list?.hideDone ?? false);
    if (list) setHidden(list.hidden);
  }
  function saveList() {
    const title = window.prompt("Name this list", "");
    if (!title) return;
    const list: SavedList = { id: `list_${Date.now().toString(36)}`, title, filters, search, hideDone, hidden };
    setLists((all) => [...all, list]);
    setListId(list.id);
    setMenu(false);
  }
  function dropList() {
    setLists((all) => all.filter((l) => l.id !== listId));
    applyList("all");
    setMenu(false);
  }

  const shownColumns = columns.filter((c) => byName.has(c));
  const openRow = openId ? (rows?.find((r) => r.id === openId) ?? null) : null;
  const filtered = Boolean(search || Object.values(filters).some(Boolean) || hideDone);
  const quick = page?.quick_entry ?? null;

  return (
    <div className="stack" aria-label={humanize(collection.name)}>
      {quick ? <Block block={{ kind: "quick_entry", action: quick.action, input: quick.input, placeholder: quick.placeholder, voice: true, extra: {} }} /> : null}
      <div className="card">
        <div className="toolbar toolbar--page">
          <div className="toggle toggle--views" role="tablist" aria-label="View">
            {VIEWS.filter((v) => v.id === "table" || v.id === "list" || (v.id === "board" && groupField) || ((v.id === "calendar" || v.id === "chart") && dateField)).map((v) => (
              <button key={v.id} type="button" role="tab" aria-selected={view === v.id} onClick={() => setView(v.id)}>
                {v.label}
              </button>
            ))}
          </div>
          {lists.length ? (
            <select className="btn btn--sm" value={listId} onChange={(e) => applyList(e.target.value)} aria-label="Saved list">
              <option value="all">All</option>
              {lists.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.title}
                </option>
              ))}
            </select>
          ) : null}
          {searchable.length ? (
            <div className="search">
              <span aria-hidden="true">⌕</span>
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search" aria-label="Search" />
            </div>
          ) : null}
          {facets.map((field) => (
            <select key={field.name} className="btn btn--sm" value={filters[field.name] ?? ""} onChange={(e) => setFilters((p) => ({ ...p, [field.name]: e.target.value }))} aria-label={`Filter by ${humanize(field.name).toLowerCase()}`}>
              <option value="">{humanize(field.name)}: any</option>
              {(field.choices ?? []).map((c) => (
                <option key={c} value={c}>
                  {humanize(c)}
                </option>
              ))}
            </select>
          ))}
          {statusField && (statusField.done_choices ?? []).length ? (
            <label className="check">
              <input type="checkbox" checked={hideDone} onChange={(e) => setHideDone(e.target.checked)} /> Hide done
            </label>
          ) : null}
          <span className="spacer" />
          <button type="button" className="btn btn--sm btn--primary" onClick={() => setAdding((a) => !a)} aria-expanded={adding}>
            {adding ? "Cancel" : "Add"}
          </button>
          <div className="menu">
            <button type="button" className="btn btn--sm btn--ghost" aria-label="More" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>
              ⋯
            </button>
            {menu ? (
              <div className="menu__list" role="menu">
                <div className="menu__head">Columns</div>
                {[...shownColumns, ...fields.map((f) => f.name).filter((n) => !shownColumns.includes(n))].map((name) => {
                  const at = shownColumns.indexOf(name);
                  return (
                    <div key={name} className="menu__item menu__item--col">
                      <label>
                        <input type="checkbox" checked={at >= 0} onChange={(e) => setHidden((h) => (e.target.checked ? h.filter((n) => n !== name) : [...h, name]))} /> {humanize(name)}
                      </label>
                      {at >= 0 ? (
                        <span className="menu__arrows">
                          <button type="button" className="iconbtn" aria-label={`Move ${humanize(name)} left`} disabled={at === 0} onClick={() => moveColumn(name, -1)}>
                            ↑
                          </button>
                          <button type="button" className="iconbtn" aria-label={`Move ${humanize(name)} right`} disabled={at === shownColumns.length - 1} onClick={() => moveColumn(name, 1)}>
                            ↓
                          </button>
                        </span>
                      ) : null}
                    </div>
                  );
                })}
                {Object.keys(widths).length ? (
                  <button type="button" className="menu__item" role="menuitem" onClick={() => setWidths({})}>
                    Reset column widths
                  </button>
                ) : null}
                <div className="menu__head">Lists</div>
                <button type="button" className="menu__item" role="menuitem" onClick={saveList} disabled={!filtered && !shownColumns.length}>
                  Save the current filters as a list
                </button>
                {listId !== "all" ? (
                  <button type="button" className="menu__item" role="menuitem" onClick={dropList}>
                    Remove this list
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
        {adding ? <AddRow fields={fields} collection={collection.name} onDone={() => setAdding(false)} onAdd={(values) => mutate({ op: "create", collection: collection.name, values }, "Could not add it")} /> : null}
        {error ? (
          <p className="notice" style={{ padding: 12 }} role="alert">
            {error}{" "}
            <button type="button" className="btn btn--sm" onClick={load}>
              Try again
            </button>
          </p>
        ) : null}
        {view === "table" ? (
          <TableView rows={rows ?? []} fields={fields} columns={shownColumns} byName={byName} widths={widths} onWidth={(name, w) => setWidths((all) => ({ ...all, [name]: w }))} sort={sort} onSort={setSort} openId={openId} onOpen={setOpenId} onCommit={commit} empty={rows && !rows.length ? (filtered ? "Nothing matches." : "Nothing here yet.") : null} />
        ) : null}
        {view === "board" && groupField ? <BoardView rows={rows ?? []} field={groupField} titleField={titleField} fields={fields} onOpen={setOpenId} onMove={(row, value) => move(row, groupField, value)} /> : null}
        {view === "list" ? <ListView rows={rows ?? []} titleField={titleField} columns={shownColumns} byName={byName} onOpen={setOpenId} /> : null}
        {view === "calendar" && dateField ? <CalendarView rows={rows ?? []} field={dateField} titleField={titleField} month={month} onMonth={setMonth} onOpen={setOpenId} /> : null}
        {view === "chart" && dateField ? <ChartView rows={rows ?? []} dateField={dateField} valueField={numericField ?? null} /> : null}
        {openRow ? <RecordPanel row={openRow} fields={fields} titleField={titleField} onClose={() => setOpenId(null)} onCommit={(field, text) => commit(openRow, field, text)} onRemove={() => remove(openRow)} /> : null}
        <div className="pager">
          <span>{rows ? `${rows.length} shown` : "Loading…"}</span>
          {status ? (
            <span className={status.ok ? "notice notice--ok" : "notice"} role="status">
              {status.text}
            </span>
          ) : null}
          <span className="spacer" />
          <button type="button" className="btn btn--sm" disabled={cursors.length <= 1} onClick={() => setCursors((c) => c.slice(0, -1))}>
            Previous
          </button>
          <button type="button" className="btn btn--sm" disabled={!next} onClick={() => setCursors((c) => [...c, next])}>
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------- table ----------

function TableView({ rows, fields, columns, byName, widths, onWidth, sort, onSort, openId, onOpen, onCommit, empty }: { rows: RecordRow[]; fields: FieldInfo[]; columns: string[]; byName: Map<string, FieldInfo>; widths: Record<string, number>; onWidth: (name: string, width: number) => void; sort: { field: string; direction: "asc" | "desc" } | null; onSort: (s: { field: string; direction: "asc" | "desc" } | null) => void; openId: string | null; onOpen: (id: string) => void; onCommit: (row: RecordRow, field: FieldInfo, text: string) => void; empty: string | null }) {
  const totals = columns.filter((c) => isNumeric(byName.get(c)?.kind ?? "")).map((c) => ({ field: c, value: rows.reduce((sum, r) => sum + (typeof r.values[c] === "number" ? (r.values[c] as number) : 0), 0) }));
  return (
    <div className="tablewrap">
      <table className="table" aria-label={undefined}>
        <thead>
          <tr>
            {columns.map((c) => {
              const kind = byName.get(c)?.kind ?? "text";
              return (
                <th key={c} className={isNumeric(kind) ? "r th--sizable" : "th--sizable"} style={widths[c] ? { width: widths[c], minWidth: widths[c], maxWidth: widths[c] } : undefined} aria-sort={sort?.field === c ? (sort.direction === "asc" ? "ascending" : "descending") : undefined}>
                  <button type="button" onClick={() => onSort(sort?.field === c ? (sort.direction === "asc" ? { field: c, direction: "desc" } : null) : { field: c, direction: "asc" })}>
                    {humanize(c)}
                    {sort?.field === c ? (sort.direction === "asc" ? " ↑" : " ↓") : ""}
                  </button>
                  <span
                    className="th__grip"
                    role="separator"
                    aria-orientation="vertical"
                    aria-label={`Resize ${humanize(c)}`}
                    onClick={(e) => e.stopPropagation()}
                    onPointerDown={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      const th = (e.currentTarget as HTMLElement).parentElement as HTMLElement;
                      const startX = e.clientX;
                      const startW = th.getBoundingClientRect().width;
                      const onMove = (ev: PointerEvent) => onWidth(c, Math.max(64, Math.round(startW + ev.clientX - startX)));
                      const onUp = () => {
                        window.removeEventListener("pointermove", onMove);
                        window.removeEventListener("pointerup", onUp);
                      };
                      window.addEventListener("pointermove", onMove);
                      window.addEventListener("pointerup", onUp);
                    }}
                  />
                </th>
              );
            })}
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className={`row--open${openId === row.id ? " row--current" : ""}`} onClick={() => onOpen(row.id)} aria-label={`Open ${String(row.values[fields[0]?.name] ?? row.id)}`}>
              {columns.map((c) => (
                <Cell key={c} row={row} field={byName.get(c)!} onCommit={(text) => onCommit(row, byName.get(c)!, text)} />
              ))}
              <td className="r">
                <span className="faint">›</span>
              </td>
            </tr>
          ))}
          {empty ? (
            <tr>
              <td colSpan={columns.length + 1} className="empty" style={{ whiteSpace: "normal" }}>
                {empty}
              </td>
            </tr>
          ) : null}
        </tbody>
        {totals.length && rows.length > 1 ? (
          <tfoot>
            <tr>
              {columns.map((c, i) => {
                const t = totals.find((x) => x.field === c);
                return (
                  <td key={c} className={t ? "r num" : undefined}>
                    {t ? formatNumber(t.value) : i === 0 ? "Total" : ""}
                  </td>
                );
              })}
              <td />
            </tr>
          </tfoot>
        ) : null}
      </table>
    </div>
  );
}

/** Titles of related records, fetched once per module and record. */
const relatedTitles = new Map<string, string>();

/** A relation to another module's record: its title, and a picker over that collection. */
function RelationCell({ row, field, onCommit }: { row: RecordRow; field: FieldInfo; onCommit: (text: string) => void }) {
  const { client, detail } = useModule();
  const value = row.values[field.name];
  const key = `${field.module}/${field.collection}/${String(value ?? "")}`;
  const [title, setTitle] = useState<string | null>(() => relatedTitles.get(key) ?? null);
  const [picking, setPicking] = useState(false);
  const [options, setOptions] = useState<{ id: string; title: string }[] | null>(null);
  useEffect(() => {
    if (!value || !field.module || !field.collection || relatedTitles.has(key) || !isConnectionsClient(client)) return;
    let cancelled = false;
    client
      .relatedGet(detail.app_id, field.module, field.collection, String(value))
      .then((r) => {
        relatedTitles.set(key, r.title);
        if (!cancelled) setTitle(r.title);
      })
      .catch(() => {
        if (!cancelled) setTitle(String(value));
      });
    return () => {
      cancelled = true;
    };
  }, [client, detail.app_id, field.module, field.collection, key, value]);
  async function open(e: { stopPropagation: () => void }) {
    e.stopPropagation();
    if (!field.module || !field.collection || !isConnectionsClient(client)) return;
    setPicking(true);
    try {
      setOptions(await client.relatedPick(detail.app_id, field.module, field.collection));
    } catch {
      setOptions([]);
    }
  }
  if (picking) {
    return (
      <td onClick={(e) => e.stopPropagation()}>
        <select
          autoFocus
          value={String(value ?? "")}
          aria-label={humanize(field.name)}
          onChange={(e) => {
            const chosen = options?.find((o) => o.id === e.target.value);
            if (chosen) relatedTitles.set(`${field.module}/${field.collection}/${chosen.id}`, chosen.title);
            setPicking(false);
            onCommit(e.target.value);
          }}
          onBlur={() => setPicking(false)}
        >
          <option value="">—</option>
          {(options ?? []).map((o) => (
            <option key={o.id} value={o.id}>
              {o.title}
            </option>
          ))}
        </select>
      </td>
    );
  }
  return (
    <td className="editable" onClick={(e) => void open(e)} tabIndex={0} title="Click to choose">
      {value ? <span className="pill pill--info">{title ?? "…"}</span> : <span className="faint">—</span>}
    </td>
  );
}

function Cell({ row, field, onCommit }: { row: RecordRow; field: FieldInfo; onCommit: (text: string) => void }) {
  const [editing, setEditing] = useState(false);
  if (field.kind === "relation") return <RelationCell row={row} field={field} onCommit={onCommit} />;
  const [text, setText] = useState("");
  const value = row.values[field.name];
  const numeric = isNumeric(field.kind);
  const estimate = row.provenance?.[field.name]?.source === "model_estimate";
  function begin(e?: { stopPropagation: () => void }) {
    e?.stopPropagation();
    setText(editText(value, field.kind));
    setEditing(true);
  }
  function finish(commit: boolean) {
    setEditing(false);
    if (commit) onCommit(text);
  }
  function key(e: KeyboardEvent) {
    if (e.key === "Enter" && field.kind !== "long_text") finish(true);
    if (e.key === "Escape") finish(false);
  }
  const label = humanize(field.name);
  if (editing) {
    return (
      <td className={numeric ? "r" : undefined} onClick={(e) => e.stopPropagation()}>
        {field.kind === "choice" || field.kind === "status" ? (
          <select autoFocus value={text} onChange={(e) => setText(e.target.value)} onBlur={() => finish(true)} onKeyDown={key} aria-label={label}>
            <option value="">—</option>
            {(field.choices ?? []).map((c) => (
              <option key={c} value={c}>
                {humanize(c)}
              </option>
            ))}
          </select>
        ) : field.kind === "boolean" ? (
          <select autoFocus value={text || "false"} onChange={(e) => setText(e.target.value)} onBlur={() => finish(true)} onKeyDown={key} aria-label={label}>
            <option value="false">No</option>
            <option value="true">Yes</option>
          </select>
        ) : field.kind === "long_text" ? (
          <textarea autoFocus rows={3} value={text} onChange={(e) => setText(e.target.value)} onBlur={() => finish(true)} onKeyDown={key} aria-label={label} />
        ) : (
          <input autoFocus type={inputType(field.kind)} step={field.kind === "number" ? "any" : undefined} value={text} onChange={(e) => setText(e.target.value)} onFocus={(e) => e.currentTarget.select()} onBlur={() => finish(true)} onKeyDown={key} aria-label={label} placeholder={field.kind === "multiselect" ? (field.choices ?? []).join(", ") : undefined} />
        )}
      </td>
    );
  }
  const words = showValue(value, field.kind);
  return (
    <td className={`${numeric ? "r num" : ""} editable`.trim()} onClick={(e) => begin(e)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && begin(e)} title="Click to edit">
      {words === "" ? <span className="faint">—</span> : field.kind === "url" ? <a href={String(value)} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>{words}</a> : field.kind === "status" || field.kind === "choice" ? <span className={`pill ${field.done_choices?.includes(String(value)) ? "pill--good" : "pill--gray"}`}>{words}</span> : field.kind === "boolean" ? (value ? "✓" : <span className="faint">—</span>) : words}
      {estimate ? (
        <span className="est" title="An estimate. Click the cell to correct it." aria-label="estimate">
          ≈
        </span>
      ) : null}
    </td>
  );
}

// ---------- add ----------

function AddRow({ fields, collection, onAdd, onDone }: { fields: FieldInfo[]; collection: string; onAdd: (values: Record<string, unknown>) => Promise<boolean>; onDone: () => void }) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const first = useRef<HTMLInputElement>(null);
  useEffect(() => first.current?.focus(), []);
  async function submit(e: FormEvent) {
    e.preventDefault();
    const values: Record<string, unknown> = {};
    for (const f of fields) {
      const text = draft[f.name] ?? "";
      if (f.kind === "boolean") values[f.name] = text === "true";
      else if (text.trim() !== "") values[f.name] = coerce(text, f.kind);
    }
    setBusy(true);
    const ok = await onAdd(values);
    setBusy(false);
    if (ok) {
      setDraft({});
      onDone();
    }
  }
  const set = (name: string, value: string) => setDraft((d) => ({ ...d, [name]: value }));
  return (
    <form className="addrow" onSubmit={submit} aria-label={`Add to ${humanize(collection)}`}>
      {fields.map((f, i) => {
        const id = `add-${collection}-${f.name}`;
        const label = `${humanize(f.name)}${f.required ? "" : " (optional)"}`;
        return (
          <div key={f.name} className="field field--compact">
            <label htmlFor={id}>{label}</label>
            {f.kind === "choice" || f.kind === "status" ? (
              <select id={id} value={draft[f.name] ?? ""} onChange={(e) => set(f.name, e.target.value)}>
                <option value="">Choose…</option>
                {(f.choices ?? []).map((c) => (
                  <option key={c} value={c}>
                    {humanize(c)}
                  </option>
                ))}
              </select>
            ) : f.kind === "boolean" ? (
              <select id={id} value={draft[f.name] ?? "false"} onChange={(e) => set(f.name, e.target.value)}>
                <option value="false">No</option>
                <option value="true">Yes</option>
              </select>
            ) : f.kind === "long_text" ? (
              <textarea id={id} rows={3} value={draft[f.name] ?? ""} onChange={(e) => set(f.name, e.target.value)} />
            ) : (
              <input ref={i === 0 ? first : undefined} id={id} type={inputType(f.kind)} step={f.kind === "number" ? "any" : undefined} value={draft[f.name] ?? ""} onChange={(e) => set(f.name, e.target.value)} placeholder={f.kind === "multiselect" ? (f.choices ?? []).join(", ") : undefined} />
            )}
          </div>
        );
      })}
      <div className="row">
        <button type="submit" className="btn btn--primary btn--sm" disabled={busy}>
          Add
        </button>
        <button type="button" className="btn btn--sm" onClick={onDone}>
          Cancel
        </button>
      </div>
    </form>
  );
}

// ---------- board ----------

function BoardView({ rows, field, titleField, fields, onOpen, onMove }: { rows: RecordRow[]; field: FieldInfo; titleField: string | undefined; fields: FieldInfo[]; onOpen: (id: string) => void; onMove: (row: RecordRow, value: string) => void }) {
  const [over, setOver] = useState<string | null>(null);
  const columns = field.choices ?? [];
  const extras = fields.filter((f) => f.name !== titleField && f.name !== field.name).slice(0, 2);
  function drop(e: DragEvent, column: string) {
    e.preventDefault();
    setOver(null);
    const id = e.dataTransfer.getData("text/plain");
    const row = rows.find((r) => r.id === id);
    if (row) onMove(row, column);
  }
  return (
    <div className="board board--page">
      {columns.map((column) => {
        const cards = rows.filter((r) => String(r.values[field.name] ?? "") === column);
        const done = field.done_choices?.includes(column);
        return (
          <div key={column} className={`board__col${over === column ? " board__col--over" : ""}${done ? " board__col--done" : ""}`} onDragOver={(e) => { e.preventDefault(); setOver(column); }} onDragLeave={() => setOver(null)} onDrop={(e) => drop(e, column)} aria-label={humanize(column)}>
            <h4>
              {humanize(column)} <span>{cards.length}</span>
            </h4>
            {cards.map((row) => (
              <button key={row.id} type="button" className="board__card" draggable onDragStart={(e) => e.dataTransfer.setData("text/plain", row.id)} onClick={() => onOpen(row.id)}>
                <b>{titleField ? String(row.values[titleField] ?? "Untitled") : row.id}</b>
                {extras.map((f) => (
                  <span key={f.name} className="faint">
                    {showValue(row.values[f.name], f.kind)}
                  </span>
                ))}
              </button>
            ))}
            {!cards.length ? <p className="empty" style={{ padding: 12 }}>Nothing here</p> : null}
          </div>
        );
      })}
    </div>
  );
}

// ---------- list ----------

function ListView({ rows, titleField, columns, byName, onOpen }: { rows: RecordRow[]; titleField: string | undefined; columns: string[]; byName: Map<string, FieldInfo>; onOpen: (id: string) => void }) {
  const secondary = columns.filter((c) => c !== titleField).slice(0, 3);
  if (!rows.length) return <p className="empty">Nothing here yet.</p>;
  return (
    <div className="list">
      {rows.map((row) => (
        <button key={row.id} type="button" className="list__row" onClick={() => onOpen(row.id)}>
          <b>{titleField ? String(row.values[titleField] ?? "Untitled") : row.id}</b>
          <span className="faint">
            {secondary
              .map((c) => showValue(row.values[c], byName.get(c)?.kind ?? "text"))
              .filter(Boolean)
              .join(" · ")}
          </span>
        </button>
      ))}
    </div>
  );
}

// ---------- calendar ----------

function CalendarView({ rows, field, titleField, month, onMonth, onOpen }: { rows: RecordRow[]; field: FieldInfo; titleField: string | undefined; month: { y: number; m: number }; onMonth: (m: { y: number; m: number }) => void; onOpen: (id: string) => void }) {
  const first = new Date(month.y, month.m, 1);
  const start = (first.getDay() + 6) % 7; // Monday first
  const days = new Date(month.y, month.m + 1, 0).getDate();
  const cells: (number | null)[] = [...Array(start).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  while (cells.length % 7) cells.push(null);
  const byDay = new Map<string, RecordRow[]>();
  for (const row of rows) {
    const raw = row.values[field.name];
    if (typeof raw !== "string") continue;
    const day = raw.slice(0, 10);
    byDay.set(day, [...(byDay.get(day) ?? []), row]);
  }
  const label = first.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  return (
    <div className="calendar">
      <div className="calendar__head">
        <button type="button" className="btn btn--sm btn--ghost" onClick={() => onMonth(month.m === 0 ? { y: month.y - 1, m: 11 } : { y: month.y, m: month.m - 1 })} aria-label="Previous month">
          ‹
        </button>
        <b>{label}</b>
        <button type="button" className="btn btn--sm btn--ghost" onClick={() => onMonth(month.m === 11 ? { y: month.y + 1, m: 0 } : { y: month.y, m: month.m + 1 })} aria-label="Next month">
          ›
        </button>
      </div>
      <div className="calendar__grid">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
          <div key={d} className="calendar__dow">
            {d}
          </div>
        ))}
        {cells.map((day, i) => {
          const iso = day ? `${month.y}-${String(month.m + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}` : "";
          const items = day ? (byDay.get(iso) ?? []) : [];
          return (
            <div key={i} className={`calendar__day${day ? "" : " calendar__day--pad"}`}>
              {day ? <span className="calendar__num">{day}</span> : null}
              {items.slice(0, 3).map((row) => (
                <button key={row.id} type="button" className="calendar__chip" onClick={() => onOpen(row.id)}>
                  {titleField ? String(row.values[titleField] ?? "Untitled") : row.id}
                </button>
              ))}
              {items.length > 3 ? <span className="faint">+{items.length - 3}</span> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------- chart ----------

function ChartView({ rows, dateField, valueField }: { rows: RecordRow[]; dateField: FieldInfo; valueField: FieldInfo | null }) {
  const [measure, setMeasure] = useState<string>(valueField?.name ?? "count");
  const byDay = new Map<string, number>();
  for (const row of rows) {
    const raw = row.values[dateField.name];
    if (typeof raw !== "string") continue;
    const day = raw.slice(0, 10);
    const add = measure === "count" ? 1 : typeof row.values[measure] === "number" ? (row.values[measure] as number) : 0;
    byDay.set(day, (byDay.get(day) ?? 0) + add);
  }
  const days = [...byDay.keys()].sort().slice(-31);
  const max = Math.max(1, ...days.map((d) => byDay.get(d) ?? 0));
  return (
    <div className="chart">
      <div className="chart__head">
        <span className="faint">Per day, over the entries shown</span>
        <select className="btn btn--sm" value={measure} onChange={(e) => setMeasure(e.target.value)} aria-label="What to chart">
          <option value="count">Count</option>
          {valueField ? <option value={valueField.name}>{humanize(valueField.name)}</option> : null}
        </select>
      </div>
      {days.length ? (
        <div className="chart__bars" role="img" aria-label={`${humanize(measure)} per day`}>
          {days.map((d) => {
            const v = byDay.get(d) ?? 0;
            return (
              <div key={d} className="chart__bar" title={`${d}: ${formatNumber(v)}`}>
                <div className="chart__fill" style={{ height: `${Math.round((v / max) * 100)}%` }} />
                <span className="chart__label">{d.slice(8)}</span>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="empty">Nothing to chart yet.</p>
      )}
    </div>
  );
}

// ---------- record page ----------

function RecordPanel({ row, fields, titleField, onClose, onCommit, onRemove }: { row: RecordRow; fields: FieldInfo[]; titleField: string | undefined; onClose: () => void; onCommit: (field: FieldInfo, text: string) => void; onRemove: () => void }) {
  const title = titleField ? String(row.values[titleField] ?? "") : "";
  const long = fields.filter((f) => f.kind === "long_text");
  const shown = fields.filter((f) => f.name !== titleField && f.kind !== "long_text");
  const when = (iso: string) => (iso ? new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "");
  return (
    <section className="drawer" aria-label={title || "Details"}>
      <div className="drawer__head">
        <h3>{title || "Details"}</h3>
        <span className="spacer" />
        <button type="button" className="btn btn--sm btn--danger" onClick={onRemove}>
          Remove
        </button>
        <button type="button" className="btn btn--sm btn--ghost" onClick={onClose} aria-label="Close details">
          ✕
        </button>
      </div>
      <table className="table table--kv">
        <tbody>
          {shown.map((f) => (
            <tr key={f.name}>
              <th scope="row">{humanize(f.name)}</th>
              <Cell row={row} field={f} onCommit={(text) => onCommit(f, text)} />
            </tr>
          ))}
          {row.created_at ? (
            <tr>
              <th scope="row">Added</th>
              <td>{when(row.created_at)}</td>
            </tr>
          ) : null}
          {row.updated_at && row.updated_at !== row.created_at ? (
            <tr>
              <th scope="row">Last changed</th>
              <td>{when(row.updated_at)}</td>
            </tr>
          ) : null}
        </tbody>
      </table>
      {long.map((f) => (
        <div key={f.name} className="drawer__long">
          <h4>{humanize(f.name)}</h4>
          <LongText value={row.values[f.name]} onCommit={(text) => onCommit(f, text)} />
        </div>
      ))}
    </section>
  );
}

function LongText({ value, onCommit }: { value: unknown; onCommit: (text: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  if (editing) {
    return (
      <textarea autoFocus rows={6} value={text} onChange={(e) => setText(e.target.value)} onBlur={() => { setEditing(false); onCommit(text); }} aria-label="Edit text" />
    );
  }
  return (
    <p className="editable" onClick={() => { setText(value ? String(value) : ""); setEditing(true); }} title="Click to edit">
      {value ? String(value) : <span className="faint">Nothing yet. Click to write.</span>}
    </p>
  );
}
