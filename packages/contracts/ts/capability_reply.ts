/* Generated from capability_reply.schema.json (contract 0.2). Do not edit. */

export interface CapabilityReply {
  call_id: string;
  error?: CapabilityError | null;
  kind?: "reply";
  result?: {
    [k: string]: unknown;
  };
  status: "completed" | "failed";
}
export interface CapabilityError {
  code:
    | "invalid_input"
    | "not_found"
    | "conflict"
    | "forbidden"
    | "unauthenticated"
    | "limit_exceeded"
    | "unavailable"
    | "timed_out"
    | "internal_error";
  details?: {
    [k: string]: unknown;
  };
  message: string;
}
