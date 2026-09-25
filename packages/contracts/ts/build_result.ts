/* Generated from build_result.schema.json (contract 0.2). Do not edit. */

export type FailureCategory =
  | "harness_unavailable"
  | "harness_auth"
  | "harness_error"
  | "harness_timeout"
  | "budget_exhausted"
  | "no_package"
  | "invalid_package"
  | "validation_failed"
  | "cancelled"
  | "interrupted";
export type BuildResultStatus = "candidate" | "failed" | "cancelled";
export type CostBasis = "provider_reported" | "subscription_unmetered" | "unavailable";

export interface BuildResult {
  attempt_id: string;
  build_id: string;
  contract_version?: "0.2";
  diagnostics?: BuildDiagnostic[];
  failure_category?: FailureCategory | null;
  finished_at: string;
  harness: string;
  model_route_ref: string;
  source_digest?: string | null;
  source_package_ref?: string | null;
  started_at: string;
  status: BuildResultStatus;
  usage?: BuildUsage | null;
}
export interface BuildDiagnostic {
  code: string;
  level: "info" | "warning" | "error";
  message: string;
}
export interface BuildUsage {
  cache_creation_input_tokens?: number;
  cache_read_input_tokens?: number;
  cost_basis: CostBasis;
  cost_usd?: number | null;
  duration_ms?: number;
  input_tokens?: number;
  models?: {
    [k: string]: {
      [k: string]: unknown;
    };
  };
  output_tokens?: number;
  turns?: number;
}
