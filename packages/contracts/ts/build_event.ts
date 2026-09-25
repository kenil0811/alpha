/* Generated from build_event.schema.json (contract 0.2). Do not edit. */

export interface BuildEvent {
  attempt_id?: string | null;
  build_id: string;
  contract_version?: "0.2";
  event_id: string;
  kind: string;
  occurred_at: string;
  payload: {
    [k: string]: unknown;
  };
  sequence: number;
}
