/* Generated from skill_run.schema.json (contract 0.2). Do not edit. */

export interface SkillRun {
  evidence?: {
    [k: string]: unknown;
  }[];
  finished_at?: string | null;
  inputs: {
    [k: string]: unknown;
  };
  items?: {
    [k: string]: unknown;
  }[];
  run_id: string;
  skill_id: string;
  started_at: string;
  state: "running" | "done" | "failed";
  summary?: string;
}
