/**
 * Bridge-style table baseline for one `table` block: toolbar (Lists, view switcher, search,
 * filter, view actions), column menu, row peek, selection and Notion-like cell editing — all
 * client side over the rows the declared view already returned.
 */
import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { MoreHorizontal, PanelRight } from "lucide-react";
import { Button } from "../../ui/Button";
import { IconButton } from "../../ui/IconButton";
import { Tooltip, TooltipProvider } from "../../ui/Tooltip";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "../../ui/DropdownMenu";
import type { ActionBinding, DetailSpec, RecordPageResult, RecordRow, ScreenBlock, ScreenColumn } from "../../core/client";
import { cell, coerce, resolveDates, Status, subtitle } from "../blocks";
import { formatNumber, humanize, outcomeWords, useModule, useViewQuery, type ViewQueryBody } from "../useModule";
import { useLists } from "./useLists";
import { type FilterRule, type UserList, type ViewKind } from "./types";
import { FilterButton, FilterChips, ListsMenu, PeekShell, SearchField, ViewKindSwitcher, matches, uid, type ViewKindOption } from "./ViewToolbar";
import "./views.css";

type TableBlock = Extract<ScreenBlock, { kind: "table" }>;

export function DataView({ block }: { block: TableBlock }) {
  const { view, run, detail } = useModule();
  const spec = view(block.view);
  const collection = detail.collections.find((c) => c.name === spec?.collection);
  const kinds = useMemo(() => new Map((collection?.fields ?? []).map((f) => [f.name, f])), [collection]);
  const blockId = block.title ?? block.view;
  const { lists: userLists, upsert, remove: removeList } = useLists<UserList>(detail.app_id, blockId);

  const [listId, setListId] = useState<string>(block.lists[0]?.id ?? "all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<{ field: string; direction: "asc" | "desc" } | null>(null);
  const [filters, setFilters] = useState<FilterRule[]>([]);
  const [hiddenColumns, setHiddenColumns] = useState<string[]>([]);
  const [columnOrder, setColumnOrder] = useState<string[]>(block.columns.map((c) => c.field));
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>({});
  const [viewKind, setViewKind] = useState<ViewKind>("table");
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const activeUserList = userLists.find((l) => l.id === listId) ?? null;
  const onAll = listId === "all" || block.lists.some((l) => l.id === listId);

  // Applying a user List loads its saved state.
  function applyList(list: UserList) {
    setFilters(list.filters);
    setSort(list.sort);
    setHiddenColumns(list.hiddenColumns);
    setColumnOrder(list.columnOrder.length ? list.columnOrder : block.columns.map((c) => c.field));
    setColumnWidths(list.columnWidths);
    setViewKind(list.viewKind);
  }
  function selectList(id: string) {
    setListId(id);
    const list = userLists.find((l) => l.id === id);
    if (list) applyList(list);
    else {
      setFilters([]);
      setSort(null);
    }
  }
  // Changes made while a user List is active auto-save back to it.
  useEffect(() => {
    if (!activeUserList) return;
    upsert({ ...activeUserList, filters, sort, hiddenColumns, columnOrder, columnWidths, viewKind });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, sort, hiddenColumns, columnOrder, columnWidths, viewKind]);

  function saveAsList(title: string) {
    const list: UserList = { id: uid(), title, filters, sort, hiddenColumns, columnOrder, columnWidths, viewKind };
    upsert(list);
    setListId(list.id);
  }

  const searchable = (spec?.filterable ?? []).filter((f) => kinds.get(f)?.kind === "text");
  const body = useMemo<ViewQueryBody>(() => {
    const contract = block.lists.find((l) => l.id === listId);
    const q = search.trim();
    const parts = [];
    if (contract?.where) parts.push(resolveDates(contract.where));
    if (q && searchable.length) parts.push({ any: searchable.map((f) => ({ field: f, op: "contains", value: q })) });
    const limit = Math.min(block.page_size, spec?.max_limit ?? block.page_size);
    return { where: parts.length ? (parts.length === 1 ? parts[0] : { all: parts }) : undefined, order_by: sort ? [sort] : undefined, limit, cursor: cursors[cursors.length - 1] };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [block.lists, block.page_size, listId, search, searchable, sort, cursors, spec?.max_limit]);

  const { data, loading, error, reload } = useViewQuery<RecordPageResult>(spec ? block.view : null, body);
  const allRows = data?.records ?? [];
  const rows = useMemo(() => allRows.filter((r) => filters.every((f) => matches(r.values, f, kinds.get(f.field)?.kind ?? "text"))), [allRows, filters, kinds]);
  useEffect(() => setCursors([null]), [listId, search, sort]);

  const columns = useMemo<ScreenColumn[]>(() => {
    const byField = new Map(block.columns.map((c) => [c.field, c]));
    return columnOrder.filter((f) => byField.has(f) && !hiddenColumns.includes(f)).map((f) => byField.get(f) as ScreenColumn);
  }, [block.columns, columnOrder, hiddenColumns]);

  const choiceColumns = block.columns.filter((c) => kinds.get(c.field)?.kind === "choice" && (kinds.get(c.field)?.choices ?? []).length);
  const dateColumns = block.columns.filter((c) => kinds.get(c.field)?.kind === "date");
  const [groupField, setGroupField] = useState<string | null>(choiceColumns[0]?.field ?? null);
  const [dateField, setDateField] = useState<string | null>(dateColumns[0]?.field ?? null);

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
  async function removeRow(row: RecordRow) {
    if (!block.delete?.id_param) return;
    const words = outcomeWords(await run(block.delete.action, { ...block.delete.input, [block.delete.id_param]: row.id }), "Removed.");
    setStatus(words.ok ? null : words);
  }
  async function rowAction(row: RecordRow, binding: ActionBinding) {
    const words = outcomeWords(await run(binding.action, { ...binding.input, ...(binding.id_param ? { [binding.id_param]: row.id } : {}) }), "Done.");
    setStatus(words.ok ? null : words);
  }
  async function deleteSelected() {
    if (!block.delete) return;
    for (const row of rows.filter((r) => selected.has(r.id))) await removeRow(row);
    setSelected(new Set());
  }

  if (!spec) return <p className="notice">This screen refers to a view that is not declared.</p>;
  const openRow = openId ? (rows.find((r) => r.id === openId) ?? null) : null;

  const viewOptions: ViewKindOption<ViewKind>[] = [
    { kind: "table", label: "Table", enabled: true },
    { kind: "board", label: "Board", enabled: choiceColumns.length > 0, reason: "Needs a pill column to group by" },
    { kind: "list", label: "List", enabled: true },
    { kind: "gallery", label: "Gallery", enabled: true },
    { kind: "calendar", label: "Calendar", enabled: dateColumns.length > 0, reason: "Needs a date column" },
  ];

  return (
    <TooltipProvider delayDuration={300}>
    <div className="card dv">
      {block.title ? (
        <div className="section__head" style={{ padding: "12px 12px 0", marginBottom: 0 }}>
          <h3>{block.title}</h3>
        </div>
      ) : null}

      <div className="dv-toolbar">
        <div className="dv-toolbar__left">
          <ListsMenu
            declared={block.lists}
            userLists={userLists}
            listId={listId}
            onSelect={selectList}
            onCreate={saveAsList}
            onRename={(list, title) => upsert({ ...list, title })}
            onDuplicate={(list) => upsert({ ...list, id: uid(), title: `${list.title} copy` })}
            onDelete={(list) => removeList(list.id)}
          />

          <ViewKindSwitcher value={viewKind} options={viewOptions} onChange={setViewKind} />

          {searchable.length ? <SearchField value={search} onChange={setSearch} /> : null}
        </div>
        <div className="dv-toolbar__right">
          {onAll && filters.length ? (
            <Button size="sm" variant="ghost" onClick={() => saveAsList(`List ${userLists.length + 1}`)}>
              Save as list
            </Button>
          ) : null}
          <FilterButton columns={block.columns} kinds={kinds} setFilters={setFilters} />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <IconButton aria-label="View actions" size="sm">
                <MoreHorizontal size={14} strokeWidth={1.75} />
              </IconButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={reload}>Reload</DropdownMenuItem>
              {block.columns.map((c) => (
                <DropdownMenuItem key={c.field} onSelect={() => setHiddenColumns((h) => (h.includes(c.field) ? h.filter((f) => f !== c.field) : [...h, c.field]))}>
                  {hiddenColumns.includes(c.field) ? "Show" : "Hide"} {humanize(c.field)}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <FilterChips filters={filters} kinds={kinds} onRemove={(i) => setFilters((fs) => fs.filter((_, j) => j !== i))} />

      {error ? (
        <p className="notice" style={{ padding: 12 }} role="alert">
          {error} <button type="button" className="btn btn--sm" onClick={reload}>Try again</button>
        </p>
      ) : null}

      {selected.size ? (
        <div className="dv-selectionbar">
          <span>{selected.size} selected</span>
          {block.delete ? (
            <button type="button" className="btn btn--sm" onClick={deleteSelected}>
              Delete
            </button>
          ) : null}
          <button type="button" className="btn btn--sm btn--ghost" onClick={() => setSelected(new Set())}>
            Clear
          </button>
        </div>
      ) : null}

      {viewKind === "table" ? (
        <TableView
          block={block}
          columns={columns}
          kinds={kinds}
          rows={rows}
          sort={sort}
          setSort={setSort}
          sortable={spec.sortable}
          selected={selected}
          setSelected={setSelected}
          columnOrder={columnOrder}
          setColumnOrder={setColumnOrder}
          columnWidths={columnWidths}
          setColumnWidths={setColumnWidths}
          setHiddenColumns={setHiddenColumns}
          setFilters={setFilters}
          onCommit={commit}
          onOpen={block.detail ? (id) => setOpenId(id) : undefined}
          onRemove={block.delete ? removeRow : undefined}
          onRowAction={rowAction}
        />
      ) : viewKind === "board" && groupField ? (
        <BoardView block={block} rows={rows} kinds={kinds} groupField={groupField} choiceColumns={choiceColumns} setGroupField={setGroupField} onRowAction={rowAction} onOpen={block.detail ? (id) => setOpenId(id) : undefined} />
      ) : viewKind === "gallery" ? (
        <GalleryView block={block} columns={block.columns} kinds={kinds} rows={rows} onOpen={block.detail ? (id) => setOpenId(id) : undefined} />
      ) : viewKind === "calendar" && dateField ? (
        <CalendarView rows={rows} dateField={dateField} titleField={block.detail?.title_field ?? block.columns[0]?.field} dateColumns={dateColumns} setDateField={setDateField} onOpen={block.detail ? (id) => setOpenId(id) : undefined} />
      ) : (
        <ListRowsView block={block} columns={block.columns} kinds={kinds} rows={rows} onOpen={block.detail ? (id) => setOpenId(id) : undefined} />
      )}

      {!loading && rows.length === 0 ? <p className="empty" style={{ padding: 16 }}>{block.empty ?? (search || filters.length ? "Nothing matches." : "Nothing here yet.")}</p> : null}

      {block.detail && openRow ? (
        <Peek row={openRow} spec={block.detail} columns={block.columns} kinds={kinds} onClose={() => setOpenId(null)} onAction={(b) => rowAction(openRow, b)} onRemove={block.delete ? () => removeRow(openRow) : undefined} />
      ) : null}

      <div className="pager">
        <span>{loading ? "Loading…" : `Showing ${allRows.length} loaded${filters.length ? `, ${rows.length} match` : ""}`}</span>
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
    </TooltipProvider>
  );
}

// ---------- table ----------

interface TableViewProps {
  block: TableBlock;
  columns: ScreenColumn[];
  kinds: Map<string, { kind: string; choices?: string[] | null }>;
  rows: RecordRow[];
  sort: { field: string; direction: "asc" | "desc" } | null;
  setSort: (s: { field: string; direction: "asc" | "desc" } | null) => void;
  sortable: string[];
  selected: Set<string>;
  setSelected: (fn: (s: Set<string>) => Set<string>) => void;
  columnOrder: string[];
  setColumnOrder: (fn: (o: string[]) => string[]) => void;
  columnWidths: Record<string, number>;
  setColumnWidths: (fn: (w: Record<string, number>) => Record<string, number>) => void;
  setHiddenColumns: (fn: (h: string[]) => string[]) => void;
  setFilters: (fn: (fs: FilterRule[]) => FilterRule[]) => void;
  onCommit: (row: RecordRow, field: string, text: string) => void;
  onOpen?: (id: string) => void;
  onRemove?: (row: RecordRow) => void;
  onRowAction: (row: RecordRow, b: ActionBinding) => void;
}

function TableView({ block, columns, kinds, rows, sort, setSort, sortable, selected, setSelected, setColumnOrder, columnWidths, setColumnWidths, setHiddenColumns, setFilters, onCommit, onOpen, onRemove, onRowAction }: TableViewProps) {
  const dragField = useRef<string | null>(null);
  const [focused, setFocused] = useState<{ row: number; col: number } | null>(null);

  function move(field: string, dir: -1 | 1) {
    setColumnOrder((order) => {
      const i = order.indexOf(field);
      const j = i + dir;
      if (i === -1 || j < 0 || j >= order.length) return order;
      const next = order.slice();
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  }

  function onTableKeyDown(e: ReactKeyboardEvent<HTMLTableElement>) {
    if (!focused) return;
    const target = e.target as HTMLElement;
    if (target.tagName === "INPUT" || target.tagName === "SELECT") return;
    let { row, col } = focused;
    if (e.key === "ArrowRight") col = Math.min(columns.length - 1, col + 1);
    else if (e.key === "ArrowLeft") col = Math.max(0, col - 1);
    else if (e.key === "ArrowDown") row = Math.min(rows.length - 1, row + 1);
    else if (e.key === "ArrowUp") row = Math.max(0, row - 1);
    else return;
    e.preventDefault();
    setFocused({ row, col });
    (e.currentTarget.querySelector(`[data-cell="${row}-${col}"]`) as HTMLElement | null)?.focus();
  }

  return (
    <div className="tablewrap">
      <table className="table dv-table" onKeyDown={onTableKeyDown}>
        <thead>
          <tr>
            <th className="dv-gutter">
              <input type="checkbox" aria-label="Select all" checked={rows.length > 0 && selected.size === rows.length} onChange={(e) => setSelected(() => (e.target.checked ? new Set(rows.map((r) => r.id)) : new Set()))} />
            </th>
            {columns.map((c, ci) => {
              const kind = kinds.get(c.field)?.kind ?? "text";
              const numeric = kind === "number" || kind === "integer";
              const canSort = sortable.includes(c.field);
              const title = c.title ?? humanize(c.field);
              return (
                <th
                  key={c.field}
                  className={numeric ? "r" : undefined}
                  style={columnWidths[c.field] ? { width: columnWidths[c.field] } : undefined}
                  draggable
                  onDragStart={() => (dragField.current = c.field)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => {
                    const from = dragField.current;
                    if (!from || from === c.field) return;
                    setColumnOrder((order) => {
                      const next = order.filter((f) => f !== from);
                      next.splice(next.indexOf(c.field), 0, from);
                      return next;
                    });
                  }}
                  aria-sort={sort?.field === c.field ? (sort.direction === "asc" ? "ascending" : "descending") : undefined}
                >
                  <span
                    className="dv-th__resize"
                    role="separator"
                    aria-orientation="vertical"
                    aria-label={`Resize ${title}`}
                    draggable={false}
                    onClick={(e) => e.stopPropagation()}
                    onPointerDown={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      const th = e.currentTarget.parentElement as HTMLElement;
                      const startX = e.clientX;
                      const startW = th.getBoundingClientRect().width;
                      const move = (ev: PointerEvent) => setColumnWidths((widths) => ({ ...widths, [c.field]: Math.max(60, Math.round(startW + ev.clientX - startX)) }));
                      const up = () => {
                        window.removeEventListener("pointermove", move);
                        window.removeEventListener("pointerup", up);
                      };
                      window.addEventListener("pointermove", move);
                      window.addEventListener("pointerup", up);
                    }}
                  />
                  <div className="dv-th">
                    <span>{title}{sort?.field === c.field ? (sort.direction === "asc" ? " ↑" : " ↓") : ""}</span>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button type="button" className="dv-th__menu" aria-label={`${title} column menu`}>
                          <MoreHorizontal size={12} />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent>
                        {canSort ? (
                          <>
                            <DropdownMenuItem onSelect={() => setSort({ field: c.field, direction: "asc" })}>Sort ascending</DropdownMenuItem>
                            <DropdownMenuItem onSelect={() => setSort({ field: c.field, direction: "desc" })}>Sort descending</DropdownMenuItem>
                            <DropdownMenuSeparator />
                          </>
                        ) : null}
                        <DropdownMenuItem onSelect={() => setFilters((fs) => [...fs, { field: c.field, op: kind === "choice" ? "eq" : "contains", value: "" }])}>Filter by this</DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => setHiddenColumns((h) => [...h, c.field])}>Hide column</DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => move(c.field, -1)} disabled={ci === 0}>Move left</DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => move(c.field, 1)} disabled={ci === columns.length - 1}>Move right</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <RowMenuRow key={row.id} row={row} ri={ri} columns={columns} kinds={kinds} block={block} titleField={block.detail?.title_field ?? columns[0]?.field} onOpen={onOpen} onRemove={onRemove} onRowAction={onRowAction} onCommit={onCommit} selected={selected} setSelected={setSelected} focused={focused} setFocused={setFocused} />
          ))}
        </tbody>
        {block.totals?.length && rows.length ? (
          <tfoot>
            <tr>
              <td className="dv-gutter" />
              {columns.map((c, i) => {
                const t = block.totals!.includes(c.field)
                  ? rows.reduce((sum, r) => sum + (typeof r.values[c.field] === "number" ? (r.values[c.field] as number) : 0), 0)
                  : null;
                return (
                  <td key={c.field} className={t !== null ? "r num" : undefined}>
                    {t !== null ? formatNumber(t, c.unit) : i === 0 ? "Total" : ""}
                  </td>
                );
              })}
            </tr>
          </tfoot>
        ) : null}
      </table>
    </div>
  );
}

function RowMenuRow({ row, ri, columns, kinds, block, titleField, onOpen, onRemove, onRowAction, onCommit, selected, setSelected, setFocused }: {
  row: RecordRow;
  ri: number;
  columns: ScreenColumn[];
  kinds: Map<string, { kind: string; choices?: string[] | null }>;
  block: TableBlock;
  titleField?: string;
  onOpen?: (id: string) => void;
  onRemove?: (row: RecordRow) => void;
  onRowAction: (row: RecordRow, b: ActionBinding) => void;
  onCommit: (row: RecordRow, field: string, text: string) => void;
  selected: Set<string>;
  setSelected: (fn: (s: Set<string>) => Set<string>) => void;
  focused: { row: number; col: number } | null;
  setFocused: (f: { row: number; col: number }) => void;
}) {
  const [menuAt, setMenuAt] = useState(false);
  const rowMenu = (
    <DropdownMenuContent align="end">
      {onOpen ? <DropdownMenuItem onSelect={() => onOpen(row.id)}>Open</DropdownMenuItem> : null}
      {block.row_actions.map((b) => (
        <DropdownMenuItem key={b.action + (b.title ?? "")} onSelect={() => onRowAction(row, b)}>
          {b.title ?? humanize(b.action)}
        </DropdownMenuItem>
      ))}
      {onRemove ? <DropdownMenuItem onSelect={() => onRemove(row)}>Delete</DropdownMenuItem> : null}
    </DropdownMenuContent>
  );
  return (
    <tr
      className={`dv-row${onOpen ? " row--open" : ""}`}
      onContextMenu={(e) => { e.preventDefault(); setMenuAt(true); }}
      onClick={onOpen ? () => onOpen(row.id) : undefined}
      aria-label={onOpen ? `Open ${String(row.values[titleField ?? ""] ?? row.id)}` : undefined}
    >
      <td className="dv-gutter" onClick={(e) => e.stopPropagation()}>
        <input type="checkbox" aria-label="Select row" checked={selected.has(row.id)} onChange={(e) => setSelected((s) => { const next = new Set(s); if (e.target.checked) next.add(row.id); else next.delete(row.id); return next; })} />
        {onOpen || block.row_actions.length || onRemove ? (
          <DropdownMenu open={menuAt} onOpenChange={setMenuAt}>
            <DropdownMenuTrigger asChild>
              <button type="button" className="dv-rowmenu" aria-label="Row menu">
                <MoreHorizontal size={13} />
              </button>
            </DropdownMenuTrigger>
            {rowMenu}
          </DropdownMenu>
        ) : null}
      </td>
      {columns.map((c, ci) => (
        <Cell key={c.field} row={row} column={c} kind={kinds.get(c.field)?.kind ?? "text"} choices={kinds.get(c.field)?.choices ?? []} editable={Boolean(block.edit) && Boolean(c.editable)} onCommit={(text) => onCommit(row, c.field, text)} dataCell={`${ri}-${ci}`} onFocus={() => setFocused({ row: ri, col: ci })} onOpen={onOpen && c.field === (titleField ?? columns[0]?.field) ? () => onOpen(row.id) : undefined} />
      ))}
    </tr>
  );
}

function Cell({ row, column, kind, choices, editable, onCommit, dataCell, onFocus, onOpen }: { row: RecordRow; column: ScreenColumn; kind: string; choices: string[]; editable: boolean; onCommit: (text: string) => void; dataCell: string; onFocus: () => void; onOpen?: () => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const value = row.values[column.field];
  const numeric = kind === "number" || kind === "integer";
  const estimate = row.provenance?.[column.field]?.source === "model_estimate";
  function begin(e?: { stopPropagation: () => void }) {
    if (!editable) return;
    e?.stopPropagation();
    setText(value === null || value === undefined ? "" : String(value));
    setEditing(true);
  }
  function finish(commit: boolean) {
    setEditing(false);
    if (commit) onCommit(text);
  }
  function key(e: ReactKeyboardEvent) {
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
          <input autoFocus type={numeric ? "number" : kind === "date" ? "date" : "text"} value={text} onChange={(e) => setText(e.target.value)} onFocus={(e) => e.currentTarget.select()} onBlur={() => finish(true)} onKeyDown={key} aria-label={column.title ?? humanize(column.field)} />
        )}
      </td>
    );
  }
  const body = (
    <td
      data-cell={dataCell}
      className={`${numeric ? "r num" : ""} ${editable ? "editable" : ""}`.trim()}
      onClick={(e) => begin(e)}
      onFocus={onFocus}
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && begin(e)}
    >
      {cell(value, column.format ?? undefined, column.unit, kind)}
      {onOpen ? (
        <button
          type="button"
          className="dv-open"
          onClick={(e) => {
            e.stopPropagation();
            onOpen();
          }}
        >
          <PanelRight size={12} aria-hidden="true" />
          Open
        </button>
      ) : null}
      {estimate ? (
        <span className="est" title="An estimate. Click the cell to correct it." aria-label="estimate">
          ≈
        </span>
      ) : null}
    </td>
  );
  if (!editable) return <Tooltip content="Can't edit here yet">{body}</Tooltip>;
  return body;
}

// ---------- board / gallery / list / calendar ----------

function BoardView({ block, rows, kinds, groupField, choiceColumns, setGroupField, onRowAction, onOpen }: { block: TableBlock; rows: RecordRow[]; kinds: Map<string, { kind: string; choices?: string[] | null }>; groupField: string; choiceColumns: ScreenColumn[]; setGroupField: (f: string) => void; onRowAction: (row: RecordRow, b: ActionBinding) => void; onOpen?: (id: string) => void }) {
  const choices = kinds.get(groupField)?.choices ?? [];
  const titleField = block.detail?.title_field ?? block.columns[0]?.field;
  return (
    <div>
      <div className="dv-board-head">
        <span className="faint">Group by</span>
        <select value={groupField} onChange={(e) => setGroupField(e.target.value)}>
          {choiceColumns.map((c) => (
            <option key={c.field} value={c.field}>
              {humanize(c.field)}
            </option>
          ))}
        </select>
      </div>
      <div className="board">
        {choices.map((col) => {
          const cards = rows.filter((r) => r.values[groupField] === col);
          return (
            <div className="board__col" key={col}>
              <h4>
                {humanize(col)} <span>{cards.length}</span>
              </h4>
              {cards.map((row) => (
                <div className="card jcard" key={row.id} onClick={() => onOpen?.(row.id)}>
                  <b>{titleField ? String(row.values[titleField] ?? "") : row.id}</b>
                  {block.row_actions.map((b) => (
                    <button key={b.action + (b.title ?? "")} type="button" className="btn btn--sm" onClick={(e) => (e.stopPropagation(), onRowAction(row, b))}>
                      {b.title ?? humanize(b.action)}
                    </button>
                  ))}
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

function GalleryView({ block, columns, kinds, rows, onOpen }: { block: TableBlock; columns: ScreenColumn[]; kinds: Map<string, { kind: string; choices?: string[] | null }>; rows: RecordRow[]; onOpen?: (id: string) => void }) {
  const titleField = block.detail?.title_field ?? columns[0]?.field;
  const rest = columns.slice(1, 4);
  return (
    <div className="dv-gallery">
      {rows.map((row) => (
        <div key={row.id} className="card dv-gcard" onClick={() => onOpen?.(row.id)}>
          <b>{titleField ? String(row.values[titleField] ?? "") : row.id}</b>
          {rest.map((c) => (
            <div key={c.field} className="dv-gcard__row">
              <span className="faint">{humanize(c.field)}</span>
              {cell(row.values[c.field], c.format ?? undefined, c.unit, kinds.get(c.field)?.kind ?? "text")}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function ListRowsView({ block, columns, kinds, rows, onOpen }: { block: TableBlock; columns: ScreenColumn[]; kinds: Map<string, { kind: string; choices?: string[] | null }>; rows: RecordRow[]; onOpen?: (id: string) => void }) {
  const titleField = block.detail?.title_field ?? columns[0]?.field;
  const subFields = columns.slice(1, 3).map((c) => c.field);
  return (
    <div className="card list">
      {rows.map((row) => (
        <div className="item" key={row.id} onClick={() => onOpen?.(row.id)}>
          <div className="item__body">
            <b>{titleField ? String(row.values[titleField] ?? "") : row.id}</b>
            <div className="item__sub">{subtitle(row, subFields, kinds)}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function CalendarView({ rows, dateField, titleField, dateColumns, setDateField, onOpen }: { rows: RecordRow[]; dateField: string; titleField?: string; dateColumns: ScreenColumn[]; setDateField: (f: string) => void; onOpen?: (id: string) => void }) {
  const now = new Date();
  const [month, setMonth] = useState(now.getMonth());
  const [year, setYear] = useState(now.getFullYear());
  const byDay = new Map<string, RecordRow[]>();
  for (const r of rows) {
    const raw = r.values[dateField];
    const day = raw ? String(raw).slice(0, 10) : "";
    if (!day) continue;
    byDay.set(day, [...(byDay.get(day) ?? []), r]);
  }
  const first = new Date(year, month, 1);
  const days: (string | null)[] = Array(first.getDay()).fill(null);
  const count = new Date(year, month + 1, 0).getDate();
  for (let d = 1; d <= count; d++) days.push(`${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`);
  return (
    <div className="dv-calendar">
      <div className="dv-board-head">
        <button type="button" className="btn btn--sm" onClick={() => (month === 0 ? (setMonth(11), setYear((y) => y - 1)) : setMonth((m) => m - 1))}>
          ‹
        </button>
        <span>{new Date(year, month, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" })}</span>
        <button type="button" className="btn btn--sm" onClick={() => (month === 11 ? (setMonth(0), setYear((y) => y + 1)) : setMonth((m) => m + 1))}>
          ›
        </button>
        {dateColumns.length > 1 ? (
          <select value={dateField} onChange={(e) => setDateField(e.target.value)}>
            {dateColumns.map((c) => (
              <option key={c.field} value={c.field}>
                {humanize(c.field)}
              </option>
            ))}
          </select>
        ) : null}
      </div>
      <div className="dv-calendar__grid">
        {days.map((d, i) => (
          <div key={i} className="dv-calendar__cell">
            {d ? (
              <>
                <span className="faint">{Number(d.slice(8))}</span>
                {(byDay.get(d) ?? []).map((r) => (
                  <div key={r.id} className="dv-calendar__event" onClick={() => onOpen?.(r.id)}>
                    {titleField ? String(r.values[titleField] ?? "") : r.id}
                  </div>
                ))}
              </>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------- peek ----------

function Peek({ row, spec, columns, kinds, onClose, onAction, onRemove }: { row: RecordRow; spec: DetailSpec; columns: ScreenColumn[]; kinds: Map<string, { kind: string; choices?: string[] | null }>; onClose: () => void; onAction: (b: ActionBinding) => void; onRemove?: () => void }) {
  const titleField = spec.title_field ?? columns[0]?.field;
  const title = titleField ? String(row.values[titleField] ?? "") : "";
  const long = new Set(spec.long_fields);
  const all = spec.fields.length ? spec.fields : [...kinds.keys()];
  const shown = all.filter((f) => f !== titleField && !long.has(f));
  const format = (field: string) => columns.find((c) => c.field === field)?.format ?? undefined;
  const unit = (field: string) => columns.find((c) => c.field === field)?.unit;
  const when = (iso: string) => (iso ? new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "");
  const actions = (
    <>
      {/* The module's own Remove and the built-in one do the same thing; show one. */}
      {spec.actions.filter((b) => !(onRemove && (b.title ?? "").toLowerCase() === "remove")).map((b) => (
        <button key={b.action + (b.title ?? "")} type="button" className="btn btn--sm" onClick={() => onAction(b)}>
          {b.title ?? humanize(b.action)}
        </button>
      ))}
      {onRemove ? (
        <button type="button" className="btn btn--sm btn--danger" onClick={onRemove}>
          Remove
        </button>
      ) : null}
    </>
  );
  return (
    <PeekShell title={title} onClose={onClose} actions={actions}>
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
    </PeekShell>
  );
}
