/* Generated from build_request.schema.json (contract 0.2). Do not edit. */

export type CostBasis = "provider_reported" | "subscription_unmetered" | "unavailable";

export interface BuildRequest {
  attempt_id: string;
  attempt_number: number;
  base_release_ref?: string | null;
  brief_ref: string;
  budget: BuildBudget;
  build_id: string;
  context_snapshot_ref: string;
  contract_version?: "0.2";
  deadline: string;
  dependency_profile: string;
  model_route_ref: string;
  sdk_profile: string;
  template_profile: string;
  ui_kit_profile?: string | null;
  validation_plan_ref: string;
  workspace_lease_ref: string;
}
export interface BuildBudget {
  cost_basis: CostBasis;
  max_attempt_seconds: number;
  max_cost_usd?: number | null;
  max_repair_attempts: number;
  max_total_seconds: number;
  max_turns: number;
}
