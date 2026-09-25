/* Generated from aggregate_result.schema.json (contract 0.2). Do not edit. */

export interface AggregateResult {
  groups: AggregateGroup[];
  truncated?: boolean;
}
export interface AggregateGroup {
  key: {
    [k: string]: unknown;
  };
  values: {
    [k: string]: number | string | null;
  };
}
