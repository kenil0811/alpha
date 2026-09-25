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
 * F05 adds the exact code/dependency identities of generated App computation (never
 * re-resolved at invocation); later tickets add grants and provider routes.
 */
export interface ExecutionSnapshot {
  capabilities?: string[];
  dependency_manifest_sha256?: string | null;
  input_digest: string;
  limits: RunLimits;
  package_sha256?: string | null;
  runtime_profile_id?: string | null;
  timezone?: string | null;
  version_id?: string | null;
  worker_profile: string;
}
export interface RunLimits {
  timeout_seconds: number;
}
