/* Generated from run.schema.json (contract 0.2). Do not edit. */

export type RunOrigin = "user" | "assistant" | "ui" | "trigger" | "repair_test";
export type RunState =
  | "queued"
  | "running"
  | "waiting_input"
  | "waiting_approval"
  | "waiting_connection"
  | "needs_reconciliation"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "interrupted";

export interface Run {
  contract_version?: "0.2";
  created_at: string;
  finished_at?: string | null;
  latest_sequence?: number;
  origin: RunOrigin;
  output?: {
    [k: string]: unknown;
  } | null;
  owner: AppOwner | TaskOwner;
  retry_of?: string | null;
  run_id: string;
  snapshot: ExecutionSnapshot;
  started_at?: string | null;
  state: RunState;
  terminal_reason?: string | null;
  updated_at: string;
  workspace_id: string;
}
export interface AppOwner {
  action_id: string;
  app_id: string;
  kind?: "app";
  release_id: string;
}
export interface TaskOwner {
  attempt_id: string;
  kind?: "task";
  plan_ref: string;
  task_id: string;
  task_revision_id: string;
}
/**
 * The immutable facts a run was dispatched with. F01 records the narrow synthetic path;
 * later tickets add capability bindings, grants, routes and dependency identities.
 */
export interface ExecutionSnapshot {
  input_digest: string;
  limits: RunLimits;
  worker_profile: string;
}
export interface RunLimits {
  timeout_seconds: number;
}
