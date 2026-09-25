/* Generated from record.schema.json (contract 0.2). Do not edit. */

export interface AppRecord {
  collection: string;
  contract_version?: "0.2";
  created_at: string;
  id: string;
  provenance?: {
    [k: string]: FieldProvenance;
  };
  revision: number;
  updated_at: string;
  values: {
    [k: string]: unknown;
  };
}
/**
 * Where a field's current value came from when it was not typed by a person or computed by
 * the App's own rules. Model output is always an estimate the person can correct.
 */
export interface FieldProvenance {
  at: string;
  call_id?: string | null;
  model?: string | null;
  previous?: {
    [k: string]: unknown;
  } | null;
  route?: string | null;
  source: "model_estimate" | "user_correction";
}
