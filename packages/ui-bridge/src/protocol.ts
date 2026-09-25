/**
 * Generated-UI bridge protocol, contract 0.2 (specifications/contracts/App UI Bridge.md).
 *
 * Every message carries protocol_version, session_id, request_id and type. The host binds a
 * session to one transferred MessagePort; the client never learns anything it can broaden.
 */

export const PROTOCOL_VERSION = "0.2" as const;

export const REQUEST_TYPES = [
  "records.query",
  "action.invoke",
  "operation.observe",
  "artifact.open",
  "input.select",
  "shell.navigate",
] as const;
export type RequestType = (typeof REQUEST_TYPES)[number];

export type ErrorCode =
  | "invalid_request"
  | "unknown_session"
  | "forbidden"
  | "unsupported"
  | "not_found"
  | "revoked"
  | "throttled"
  | "internal";

export interface BridgeGrant {
  /** Declared action IDs this session may invoke. */
  actions: readonly string[];
  /** Declared read views this session may query. */
  read_views: readonly string[];
}

export interface BridgeSession {
  session_id: string;
  owner: { kind: "app"; app_id: string; release_id: string };
  grant: BridgeGrant;
  /** RFC3339 expiry; requests after it are rejected as revoked. */
  expires_at: string;
}

export interface BridgeRequest {
  protocol_version: typeof PROTOCOL_VERSION;
  session_id: string;
  request_id: string;
  type: RequestType;
  payload: Record<string, unknown>;
}

export interface BridgeResult {
  protocol_version: typeof PROTOCOL_VERSION;
  session_id: string;
  request_id: string;
  type: "result";
  data: unknown;
}

export interface BridgeErrorBody {
  code: ErrorCode;
  message: string;
  recovery?: string;
}

export interface BridgeError {
  protocol_version: typeof PROTOCOL_VERSION;
  session_id: string;
  request_id: string;
  type: "error";
  error: BridgeErrorBody;
}

export type BridgeResponse = BridgeResult | BridgeError;

/** Host → client control messages. */
export type BridgeControl =
  | {
      protocol_version: typeof PROTOCOL_VERSION;
      type: "bridge.ready";
      session_id: string;
      grant: BridgeGrant;
      expires_at: string;
    }
  | { protocol_version: typeof PROTOCOL_VERSION; type: "bridge.revoked"; session_id: string; reason: string };

/** Frame → parent-window announcement: "my listener is ready, send me a port". It carries
 *  nothing else and grants nothing; the host decides whether to attach. */
export interface BridgeHello {
  protocol_version: typeof PROTOCOL_VERSION;
  type: "bridge.hello";
}

/** Parent-window → frame handshake: carries the transferred MessagePort. */
export interface BridgeInit {
  protocol_version: typeof PROTOCOL_VERSION;
  type: "bridge.init";
  session_id: string;
}

const MAX_ID_LENGTH = 128;
const MAX_MESSAGE_BYTES = 64 * 1024;

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isId(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= MAX_ID_LENGTH;
}

export type Validation =
  | { ok: true; request: BridgeRequest }
  | { ok: false; request_id: string; error: BridgeErrorBody };

/** Validate a raw message against the request shape. Never trusts the sender for anything. */
export function validateRequest(value: unknown, expectedSession: string): Validation {
  const requestId = isPlainObject(value) && isId(value.request_id) ? value.request_id : "";
  const fail = (message: string, code: ErrorCode = "invalid_request"): Validation => ({
    ok: false,
    request_id: requestId,
    error: { code, message },
  });
  if (!isPlainObject(value)) return fail("message must be an object");
  let size = 0;
  try {
    size = JSON.stringify(value).length;
  } catch {
    return fail("message is not serializable");
  }
  if (size > MAX_MESSAGE_BYTES) return fail(`message exceeds ${MAX_MESSAGE_BYTES} bytes`);
  if (value.protocol_version !== PROTOCOL_VERSION) return fail("unsupported protocol_version");
  if (!isId(value.request_id)) return fail("request_id must be a non-empty string");
  if (!isId(value.session_id)) return fail("session_id must be a non-empty string");
  if (value.session_id !== expectedSession) return fail("session_id does not match this channel", "unknown_session");
  if (typeof value.type !== "string" || !(REQUEST_TYPES as readonly string[]).includes(value.type)) {
    return fail("unknown request type");
  }
  if (!isPlainObject(value.payload)) return fail("payload must be an object");
  const allowedKeys = new Set(["protocol_version", "session_id", "request_id", "type", "payload"]);
  for (const key of Object.keys(value)) {
    if (!allowedKeys.has(key)) return fail(`unexpected field: ${key}`);
  }
  return {
    ok: true,
    request: {
      protocol_version: PROTOCOL_VERSION,
      session_id: value.session_id,
      request_id: value.request_id,
      type: value.type as RequestType,
      payload: value.payload,
    },
  };
}
