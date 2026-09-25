/* Generated from solution_brief.schema.json (contract 0.2). Do not edit. */

export type Delivery = "answer" | "task" | "app";
export type Surface = "conversation" | "artifact" | "custom_ui" | "background" | "external_update";

export interface SolutionBrief {
  acceptance_examples: AcceptanceExample[];
  actions: ActionIntent[];
  assumptions: Assumption[];
  constraints: string[];
  contract_version?: "0.2";
  conversation_id: string;
  created_at: string;
  data_needs: DataNeed[];
  delivery: Delivery;
  goal: string;
  id: string;
  inputs: ContextInput[];
  open_questions: OpenQuestion[];
  primary_journey: JourneyStep[];
  recurrence: Recurrence | null;
  revision: number;
  selected_context_snapshot_id: string;
  success_summary: string;
  supersedes_revision?: number | null;
  surfaces: Surface[];
  unavailable_capabilities: string[];
}
export interface AcceptanceExample {
  action_id?: string | null;
  description: string;
  expected?: {
    [k: string]: unknown;
  } | null;
  input?: {
    [k: string]: unknown;
  } | null;
  kind?: "success" | "failure" | "boundary";
}
export interface ActionIntent {
  description: string;
  effect_class?: "none" | "local_write" | "external_read" | "external_write";
  id: string;
  inputs?: string[];
  outputs?: string[];
  required_capabilities?: string[];
  title: string;
}
export interface Assumption {
  source?: "model_default" | "user_answer" | "user_correction";
  text: string;
  turn_ref?: string | null;
}
export interface DataNeed {
  collection: string;
  fields: FieldNeed[];
  provenance?: string;
  purpose: string;
  retention?: string;
}
export interface FieldNeed {
  description?: string;
  kind: "text" | "number" | "boolean" | "date" | "datetime" | "choice" | "reference" | "json";
  name: string;
  required?: boolean;
}
export interface ContextInput {
  digest?: string | null;
  purpose: string;
  ref: string;
  source: string;
}
export interface OpenQuestion {
  id: string;
  options?: string[];
  question: string;
  why_it_matters: string;
}
export interface JourneyStep {
  action: string;
  expected_result: string;
}
export interface Recurrence {
  description: string;
  timezone: string;
  type: "interval" | "daily" | "weekly";
}
