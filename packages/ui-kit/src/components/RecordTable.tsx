import type { ReactNode } from "react";
import { Button } from "./controls";
import { EmptyState, ErrorState, LoadingState } from "./feedback";
import { cx } from "./layout";

export interface Column<Row> {
  id: string;
  /** Column heading, also used as the field label on narrow windows. */
  header: string;
  /** Cell content. Keep it short; long text wraps. */
  cell: (row: Row) => ReactNode;
  /** Right-aligned tabular numbers. */
  numeric?: boolean;
  /** When set, the heading becomes a sort button for this field. */
  sortField?: string;
}

export interface SortState {
  field: string;
  direction: "asc" | "desc";
}

export interface RecordTableProps<Row> {
  caption: string;
  columns: readonly Column<Row>[];
  rows: readonly Row[];
  getRowId: (row: Row) => string;
  /** Text of the button that opens a row (usually its title). Enables drill-down. */
  getRowLabel?: (row: Row) => string;
  onOpen?: (row: Row) => void;
  sort?: SortState | null;
  onSortChange?: (sort: SortState) => void;
  selectedIds?: ReadonlySet<string>;
  onSelectionChange?: (ids: Set<string>) => void;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  empty?: { title: string; message?: ReactNode; action?: ReactNode };
  /** Pagination controls, usually a <Pager>. */
  footer?: ReactNode;
}

/**
 * Compare and drill into many records. The first column opens the row (keyboard: Tab to it,
 * Enter). Sortable headings are buttons with aria-sort. On narrow windows each row becomes a
 * labelled card, so nothing scrolls sideways.
 */
export function RecordTable<Row>({
  caption,
  columns,
  rows,
  getRowId,
  getRowLabel,
  onOpen,
  sort,
  onSortChange,
  selectedIds,
  onSelectionChange,
  loading = false,
  error,
  onRetry,
  empty,
  footer,
}: RecordTableProps<Row>) {
  if (error) return <ErrorState title={`${caption} could not be loaded`} message={error} onRetry={onRetry} />;
  if (loading && rows.length === 0) return <LoadingState label={`Loading ${caption.toLowerCase()}…`} />;
  if (!loading && rows.length === 0) {
    return <EmptyState title={empty?.title ?? "Nothing here yet"} message={empty?.message} action={empty?.action} />;
  }
  const selectable = Boolean(onSelectionChange && selectedIds);
  const allSelected = selectable && rows.every((row) => selectedIds!.has(getRowId(row)));
  return (
    <div className="a-table-wrap" aria-busy={loading || undefined}>
      <table className="a-table">
        <caption>{caption}</caption>
        <thead>
          <tr>
            {selectable ? (
              <th className="a-table__select" scope="col">
                <input
                  type="checkbox"
                  aria-label={allSelected ? "Clear selection" : "Select all shown"}
                  checked={allSelected}
                  onChange={() => {
                    const next = new Set(selectedIds);
                    for (const row of rows) {
                      if (allSelected) next.delete(getRowId(row));
                      else next.add(getRowId(row));
                    }
                    onSelectionChange!(next);
                  }}
                />
              </th>
            ) : null}
            {columns.map((column) => {
              const active = sort && column.sortField && sort.field === column.sortField;
              const ariaSort = active ? (sort!.direction === "asc" ? "ascending" : "descending") : column.sortField ? "none" : undefined;
              return (
                <th key={column.id} scope="col" className={cx(column.numeric && "a-table__num")} aria-sort={ariaSort}>
                  {column.sortField && onSortChange ? (
                    <button
                      type="button"
                      className="a-table__sort"
                      onClick={() =>
                        onSortChange({
                          field: column.sortField!,
                          direction: active && sort!.direction === "asc" ? "desc" : "asc",
                        })
                      }
                    >
                      {column.header}
                      <span aria-hidden="true">{active ? (sort!.direction === "asc" ? "▲" : "▼") : "↕"}</span>
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const id = getRowId(row);
            const selected = selectable && selectedIds!.has(id);
            return (
              <tr key={id} aria-selected={selectable ? selected : undefined}>
                {selectable ? (
                  <td className="a-table__select" data-label="Selected">
                    <input
                      type="checkbox"
                      aria-label={`Select ${getRowLabel ? getRowLabel(row) : id}`}
                      checked={selected}
                      onChange={() => {
                        const next = new Set(selectedIds);
                        if (selected) next.delete(id);
                        else next.add(id);
                        onSelectionChange!(next);
                      }}
                    />
                  </td>
                ) : null}
                {columns.map((column, index) => (
                  <td key={column.id} className={cx(column.numeric && "a-table__num")} data-label={column.header}>
                    {index === 0 && onOpen ? (
                      <button type="button" className="a-table__open" onClick={() => onOpen(row)}>
                        {column.cell(row)}
                        <span className="a-visually-hidden">, open details</span>
                      </button>
                    ) : (
                      column.cell(row)
                    )}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
      {footer}
    </div>
  );
}

export interface PagerProps {
  /** "Showing 1–20" style description of the current page. */
  label: string;
  hasPrevious: boolean;
  hasNext: boolean;
  onPrevious: () => void;
  onNext: () => void;
  busy?: boolean;
}

export function Pager({ label, hasPrevious, hasNext, onPrevious, onNext, busy }: PagerProps) {
  return (
    <nav className="a-pager" aria-label="Pages">
      <span aria-live="polite">{label}</span>
      <span className="a-cluster">
        <Button small disabled={!hasPrevious || busy} onClick={onPrevious}>
          Previous page
        </Button>
        <Button small disabled={!hasNext || busy} onClick={onNext}>
          Next page
        </Button>
      </span>
    </nav>
  );
}
