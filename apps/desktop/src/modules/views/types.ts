/** Client-side view state for one table block. Lists are a frontend stopgap (see useLists). */
export type ViewKind = "table" | "board" | "list" | "gallery" | "calendar";

export interface FilterRule {
  field: string;
  op: string;
  value: string;
}

export interface UserList {
  id: string;
  title: string;
  filters: FilterRule[];
  sort: { field: string; direction: "asc" | "desc" } | null;
  hiddenColumns: string[];
  columnOrder: string[];
  columnWidths: Record<string, number>;
  viewKind: ViewKind;
}

export const OPS_BY_KIND: Record<string, { value: string; label: string }[]> = {
  text: [
    { value: "contains", label: "contains" },
    { value: "eq", label: "is" },
    { value: "empty", label: "is empty" },
  ],
  number: [
    { value: "eq", label: "=" },
    { value: "neq", label: "≠" },
    { value: "lt", label: "<" },
    { value: "gt", label: ">" },
  ],
  integer: [
    { value: "eq", label: "=" },
    { value: "neq", label: "≠" },
    { value: "lt", label: "<" },
    { value: "gt", label: ">" },
  ],
  date: [
    { value: "before", label: "before" },
    { value: "after", label: "after" },
    { value: "on", label: "on" },
  ],
  choice: [
    { value: "eq", label: "is" },
    { value: "neq", label: "is not" },
  ],
  boolean: [{ value: "eq", label: "is" }],
};

export function opsFor(kind: string): { value: string; label: string }[] {
  return OPS_BY_KIND[kind] ?? OPS_BY_KIND.text;
}
