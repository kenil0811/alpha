/* Generated from run_event.schema.json (contract 0.2). Do not edit. */

export interface RunEvent {
  contract_version?: "0.2";
  event_id: string;
  kind: string;
  occurred_at: string;
  payload: {
    [k: string]: unknown;
  };
  payload_schema_version?: "0.2";
  run_id: string;
  sequence: number;
  step_key?: string | null;
}
