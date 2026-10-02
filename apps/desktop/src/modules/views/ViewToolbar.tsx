/**
 * Presentational pieces shared by every standard table: the Lists control (declared lists plus
 * the person's own, saved via useLists), the view-kind switcher, the search box, the filter
 * builder, and the right-side peek shell. DataView and DataPage both render these so a table
 * looks and behaves the same everywhere, no matter what data layer sits under it.
 */
import { useEffect, useState, type ReactNode } from "react";
import { Filter as FilterIcon, MoreHorizontal, Search, X } from "lucide-react";
import { Button } from "../../ui/Button";
import { IconButton } from "../../ui/IconButton";
import { Tooltip } from "../../ui/Tooltip";
import { Popover, PopoverContent, PopoverTrigger } from "../../ui/Popover";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../../ui/DropdownMenu";
import { StandardDropdown } from "../../ui/StandardDropdown";
import { humanize } from "../useModule";
import { opsFor, type FilterRule } from "./types";
import "./views.css";

export function uid(): string {
  return Math.random().toString(36).slice(2, 10);
}

/** Client-side filter-rule matching, shared by every table that offers ad-hoc filters. */
export function matches(values: Record<string, unknown>, rule: FilterRule, kind: string): boolean {
  const raw = values[rule.field];
  if (rule.op === "empty") return raw === null || raw === undefined || raw === "";
  if (kind === "date" || kind === "datetime") {
    const a = raw ? String(raw) : "";
    if (rule.op === "before") return Boolean(a) && a < rule.value;
    if (rule.op === "after") return Boolean(a) && a > rule.value;
    return a === rule.value;
  }
  if (kind === "number" || kind === "integer") {
    const a = typeof raw === "number" ? raw : Number(raw);
    const b = Number(rule.value);
    if (Number.isNaN(a)) return false;
    if (rule.op === "eq") return a === b;
    if (rule.op === "neq") return a !== b;
    if (rule.op === "lt") return a < b;
    if (rule.op === "gt") return a > b;
  }
  const a = raw === null || raw === undefined ? "" : String(raw);
  if (rule.op === "contains") return a.toLowerCase().includes(rule.value.toLowerCase());
  if (rule.op === "neq") return a !== rule.value;
  return a === rule.value;
}

// ---------- lists ----------

export interface ListsMenuProps<T extends { id: string; title: string }> {
  /** Lists a block/collection declares up front; not renameable or deletable here. */
  declared?: { id: string; title: string }[];
  userLists: T[];
  listId: string;
  onSelect: (id: string) => void;
  onCreate: (title: string) => void;
  onRename: (list: T, title: string) => void;
  onDuplicate: (list: T) => void;
  onDelete: (list: T) => void;
}

/** The Lists control: a StandardDropdown of declared + user lists, "New list", and rename/duplicate/delete on the active one. */
export function ListsMenu<T extends { id: string; title: string }>({ declared = [], userLists, listId, onSelect, onCreate, onRename, onDuplicate, onDelete }: ListsMenuProps<T>) {
  const [renaming, setRenaming] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const activeUserList = userLists.find((l) => l.id === listId) ?? null;
  const options = [{ value: "all", label: "All" }, ...declared.map((l) => ({ value: l.id, label: l.title })), ...userLists.map((l) => ({ value: l.id, label: l.title }))];
  function create() {
    onCreate(newName.trim() || `List ${userLists.length + 1}`);
    setNewName("");
  }
  return (
    <>
      <StandardDropdown options={options} value={listId} onChange={onSelect} placeholder="Select list" onAdd={() => setRenaming("new")} addLabel="New list" />
      {renaming === "new" ? (
        <span className="dv-newlist">
          <input className="dv-input dv-input--sm" autoFocus placeholder="Name this list…" value={newName} onChange={(e) => setNewName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (create(), setRenaming(null))} />
          <Button size="sm" onClick={() => (create(), setRenaming(null))}>
            Create
          </Button>
        </span>
      ) : null}
      {activeUserList && renaming !== activeUserList.id ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <IconButton aria-label="List options" size="sm">
              <MoreHorizontal size={14} strokeWidth={1.75} />
            </IconButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem onSelect={() => setRenaming(activeUserList.id)}>Rename</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => onDuplicate(activeUserList)}>Duplicate</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => (onDelete(activeUserList), onSelect("all"))}>Delete</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
      {activeUserList && renaming === activeUserList.id ? (
        <input
          className="dv-input dv-input--sm"
          autoFocus
          defaultValue={activeUserList.title}
          onBlur={(e) => (onRename(activeUserList, e.target.value.trim() || activeUserList.title), setRenaming(null))}
          onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
        />
      ) : null}
    </>
  );
}

// ---------- view switcher ----------

export interface ViewKindOption<K extends string> {
  kind: K;
  label: string;
  enabled: boolean;
  reason?: string;
}

export function ViewKindSwitcher<K extends string>({ value, options, onChange }: { value: K; options: ViewKindOption<K>[]; onChange: (k: K) => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant="ghost">
          {options.find((o) => o.kind === value)?.label}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        {options.map((o) =>
          o.enabled ? (
            <DropdownMenuItem key={o.kind} onSelect={() => onChange(o.kind)}>
              {o.label}
            </DropdownMenuItem>
          ) : (
            <Tooltip key={o.kind} content={o.reason}>
              <div className="ui-menu__item ui-menu__item--disabled">{o.label}</div>
            </Tooltip>
          ),
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// ---------- search ----------

export function SearchField({ value, onChange, placeholder = "Search" }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <div className="search dv-search">
      <Search size={13} strokeWidth={1.75} aria-hidden="true" />
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} aria-label="Search" />
    </div>
  );
}

// ---------- filter builder ----------

export interface FilterColumn {
  field: string;
  title?: string | null;
}
export interface FilterKindInfo {
  kind: string;
  choices?: string[] | null;
}

export function FilterButton({ columns, kinds, setFilters }: { columns: FilterColumn[]; kinds: Map<string, FilterKindInfo>; setFilters: (fn: (fs: FilterRule[]) => FilterRule[]) => void }) {
  const [open, setOpen] = useState(false);
  const [field, setField] = useState(columns[0]?.field ?? "");
  const kind = kinds.get(field)?.kind ?? "text";
  const [op, setOp] = useState(opsFor(kind)[0]?.value ?? "contains");
  const [value, setValue] = useState("");
  function add() {
    if (!field || (!value && op !== "empty")) return;
    setFilters((fs) => [...fs, { field, op, value }]);
    setValue("");
    setOpen(false);
  }
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <IconButton aria-label="Filter" size="sm">
          <FilterIcon size={14} strokeWidth={1.75} />
        </IconButton>
      </PopoverTrigger>
      <PopoverContent align="end">
        <div className="dv-filterbuilder">
          <select value={field} onChange={(e) => (setField(e.target.value), setOp(opsFor(kinds.get(e.target.value)?.kind ?? "text")[0]?.value ?? "contains"))}>
            {columns.map((c) => (
              <option key={c.field} value={c.field}>
                {c.title ?? humanize(c.field)}
              </option>
            ))}
          </select>
          <select value={op} onChange={(e) => setOp(e.target.value)}>
            {opsFor(kind).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          {op !== "empty" ? (
            kind === "choice" ? (
              <select value={value} onChange={(e) => setValue(e.target.value)}>
                <option value="">—</option>
                {(kinds.get(field)?.choices ?? []).map((c) => (
                  <option key={c} value={c}>
                    {humanize(c)}
                  </option>
                ))}
              </select>
            ) : (
              <input type={kind === "date" ? "date" : kind === "number" || kind === "integer" ? "number" : "text"} value={value} onChange={(e) => setValue(e.target.value)} />
            )
          ) : null}
          <Button size="sm" onClick={add}>
            Add filter
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

export function FilterChips({ filters, kinds, onRemove }: { filters: FilterRule[]; kinds: Map<string, FilterKindInfo>; onRemove: (i: number) => void }) {
  if (!filters.length) return null;
  return (
    <div className="dv-chips">
      {filters.map((f, i) => (
        <span key={i} className="dv-chip">
          {humanize(f.field)} {opsFor(kinds.get(f.field)?.kind ?? "text").find((o) => o.value === f.op)?.label} {f.op !== "empty" ? f.value : ""}
          <button type="button" onClick={() => onRemove(i)} aria-label="Remove filter">
            <X size={11} strokeWidth={1.75} />
          </button>
        </span>
      ))}
    </div>
  );
}

// ---------- right-side peek shell ----------

export function PeekShell({ title, onClose, actions, children }: { title: string; onClose: () => void; actions?: ReactNode; children: ReactNode }) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <>
      <div className="dv-peek__scrim" onClick={onClose} />
      <section className="dv-peek" aria-label={title || "Details"} role="dialog">
        <div className="drawer__head">
          <h3>{title || "Details"}</h3>
          <span className="spacer" />
          {actions}
          <IconButton aria-label="Close details" size="sm" onClick={onClose}>
            <X size={14} strokeWidth={1.75} />
          </IconButton>
        </div>
        {children}
      </section>
    </>
  );
}
