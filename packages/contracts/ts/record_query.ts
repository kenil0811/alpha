/* Generated from record_query.schema.json (contract 0.2). Do not edit. */

export type FilterOp = "eq" | "ne" | "lt" | "lte" | "gt" | "gte" | "in" | "contains" | "starts_with" | "is_null";

export interface RecordQuery {
  collection: string;
  cursor?: string | null;
  fields?: string[] | null;
  limit?: number;
  /**
   * @maxItems 3
   */
  order_by?: [] | [SortKey] | [SortKey, SortKey] | [SortKey, SortKey, SortKey];
  where?: Clause | AllOf | AnyOf | Not | null;
}
export interface SortKey {
  direction?: "asc" | "desc";
  field: string;
}
export interface Clause {
  field: string;
  op: FilterOp;
  value?: {
    [k: string]: unknown;
  };
}
export interface AllOf {
  /**
   * @minItems 1
   * @maxItems 256
   */
  all: [Clause | AllOf | AnyOf | Not, ...(Clause | AllOf | AnyOf | Not)[]];
}
export interface AnyOf {
  /**
   * @minItems 1
   * @maxItems 256
   */
  any: [Clause | AllOf | AnyOf | Not, ...(Clause | AllOf | AnyOf | Not)[]];
}
export interface Not {
  not: Clause | AllOf | AnyOf | Not;
}
