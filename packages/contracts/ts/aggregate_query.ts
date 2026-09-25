/* Generated from aggregate_query.schema.json (contract 0.2). Do not edit. */

export type Bucket = "day" | "week" | "month";
export type MetricFn = "count" | "sum" | "avg" | "min" | "max";
export type FilterOp = "eq" | "ne" | "lt" | "lte" | "gt" | "gte" | "in" | "contains" | "starts_with" | "is_null";

export interface AggregateQuery {
  collection: string;
  /**
   * @maxItems 3
   */
  group_by?: [] | [GroupKey] | [GroupKey, GroupKey] | [GroupKey, GroupKey, GroupKey];
  limit?: number;
  /**
   * @minItems 1
   * @maxItems 8
   */
  metrics:
    | [Metric]
    | [Metric, Metric]
    | [Metric, Metric, Metric]
    | [Metric, Metric, Metric, Metric]
    | [Metric, Metric, Metric, Metric, Metric]
    | [Metric, Metric, Metric, Metric, Metric, Metric]
    | [Metric, Metric, Metric, Metric, Metric, Metric, Metric]
    | [Metric, Metric, Metric, Metric, Metric, Metric, Metric, Metric];
  where?: Clause | AllOf | AnyOf | Not | null;
}
export interface GroupKey {
  bucket?: Bucket | null;
  field: string;
  timezone?: string | null;
}
export interface Metric {
  field?: string | null;
  fn: MetricFn;
  name: string;
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
