/** Typed filters for declared read views (the same filter shape Core validates). A view fixes
 *  the collection, fields and limits; the UI may only narrow it with these filters. */

export type FilterOp = "eq" | "ne" | "lt" | "lte" | "gt" | "gte" | "in" | "contains" | "starts_with" | "is_null";

export type FilterNode =
  | { field: string; op: FilterOp; value?: unknown }
  | { all: FilterNode[] }
  | { any: FilterNode[] }
  | { not: FilterNode };

export interface SortKey {
  field: string;
  direction: "asc" | "desc";
}

export const eq = (field: string, value: unknown): FilterNode => ({ field, op: "eq", value });
export const ne = (field: string, value: unknown): FilterNode => ({ field, op: "ne", value });
export const lt = (field: string, value: unknown): FilterNode => ({ field, op: "lt", value });
export const lte = (field: string, value: unknown): FilterNode => ({ field, op: "lte", value });
export const gt = (field: string, value: unknown): FilterNode => ({ field, op: "gt", value });
export const gte = (field: string, value: unknown): FilterNode => ({ field, op: "gte", value });
export const oneOf = (field: string, values: unknown[]): FilterNode => ({ field, op: "in", value: values });
export const contains = (field: string, text: string): FilterNode => ({ field, op: "contains", value: text });
export const startsWith = (field: string, text: string): FilterNode => ({ field, op: "starts_with", value: text });
export const isEmpty = (field: string): FilterNode => ({ field, op: "is_null", value: true });
export const not = (node: FilterNode): FilterNode => ({ not: node });

/** AND of the given filters, ignoring undefined ones; undefined when nothing is left. */
export function allOf(...nodes: Array<FilterNode | undefined | null | false>): FilterNode | undefined {
  const kept = nodes.filter((n): n is FilterNode => Boolean(n));
  if (kept.length === 0) return undefined;
  return kept.length === 1 ? kept[0] : { all: kept };
}

export function anyOf(...nodes: Array<FilterNode | undefined | null | false>): FilterNode | undefined {
  const kept = nodes.filter((n): n is FilterNode => Boolean(n));
  if (kept.length === 0) return undefined;
  return kept.length === 1 ? kept[0] : { any: kept };
}

/** "-noted_on" → {field: "noted_on", direction: "desc"}. */
export function orderBy(...keys: string[]): SortKey[] {
  return keys.map((key) => (key.startsWith("-") ? { field: key.slice(1), direction: "desc" } : { field: key, direction: "asc" }));
}
