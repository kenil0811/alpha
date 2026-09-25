/* Generated from capability_call.schema.json (contract 0.2). Do not edit. */

export interface CapabilityCall {
  args?: {
    [k: string]: unknown;
  };
  call_id: string;
  kind?: "call";
  operation: string;
  token: string;
  version?: 1;
}
