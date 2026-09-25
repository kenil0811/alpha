/* Generated from model_estimate.schema.json (contract 0.2). Do not edit. */

export interface ModelEstimate {
  call_id: string;
  created_at: string;
  label?: "estimate";
  model: string;
  output: {
    [k: string]: unknown;
  };
  route: string;
}
