/**
 * BridgeHost: the trusted shell's end of a generated-UI session.
 *
 * One host per frame session. The host owns a MessagePort that was transferred to exactly one
 * window; the port is the identity, the session_id is a label that every message must repeat.
 * Nothing the child sends can widen the session: grants come from the host's caller, results
 * are produced by shell-side handlers, and every request is validated before dispatch.
 */

import {
  PROTOCOL_VERSION,
  validateRequest,
  type BridgeControl,
  type BridgeErrorBody,
  type BridgeInit,
  type BridgeRequest,
  type BridgeResponse,
  type BridgeSession,
  type ErrorCode,
} from "./protocol";

export interface ActionInvokePayload {
  action_id: string;
  input: Record<string, unknown>;
}

export interface OperationObservePayload {
  operation_id: string;
  after: number;
}

export interface RecordsQueryPayload {
  /** A read view the App declared; the host only forwards views granted to this session. */
  view: string;
  /** Typed filter AST narrowing the view; the platform validates it again. */
  where?: Record<string, unknown>;
  order_by?: Array<{ field: string; direction: "asc" | "desc" }>;
  limit?: number;
  cursor?: string;
}

const RECORDS_QUERY_KEYS = new Set(["view", "where", "order_by", "limit", "cursor"]);

export interface BridgeHandlers {
  actionInvoke?: (session: BridgeSession, payload: ActionInvokePayload) => Promise<{ operation_id: string }>;
  operationObserve?: (session: BridgeSession, payload: OperationObservePayload) => Promise<unknown>;
  recordsQuery?: (session: BridgeSession, payload: RecordsQueryPayload) => Promise<unknown>;
  artifactOpen?: (session: BridgeSession, payload: Record<string, unknown>) => Promise<unknown>;
  inputSelect?: (session: BridgeSession, payload: Record<string, unknown>) => Promise<unknown>;
  shellNavigate?: (session: BridgeSession, payload: Record<string, unknown>) => Promise<unknown>;
}

export interface BridgeHostEvent {
  kind: "ready" | "request" | "result" | "error" | "revoked" | "dropped";
  detail: Record<string, unknown>;
}

export interface BridgeHostOptions {
  session: BridgeSession;
  handlers: BridgeHandlers;
  now?: () => number;
  onEvent?: (event: BridgeHostEvent) => void;
  maxInFlight?: number;
}

export class BridgeError extends Error {
  constructor(
    public readonly code: ErrorCode,
    message: string,
    public readonly recovery?: string,
  ) {
    super(message);
  }
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export class BridgeHost {
  readonly session: BridgeSession;
  private readonly handlers: BridgeHandlers;
  private readonly now: () => number;
  private readonly onEvent: (event: BridgeHostEvent) => void;
  private readonly maxInFlight: number;
  private port: MessagePort | null = null;
  private revoked = false;
  private inFlight = 0;
  /** Operations created through this session; the only ones it may observe. */
  private readonly operations = new Set<string>();

  constructor(options: BridgeHostOptions) {
    this.session = options.session;
    this.handlers = options.handlers;
    this.now = options.now ?? (() => Date.now());
    this.onEvent = options.onEvent ?? (() => undefined);
    this.maxInFlight = options.maxInFlight ?? 16;
  }

  get isRevoked(): boolean {
    return this.revoked;
  }

  /** Bind to an existing port (tests, or a channel created by the caller). */
  bind(port: MessagePort): void {
    if (this.port) throw new Error("host already bound");
    this.port = port;
    port.onmessage = (event: MessageEvent) => {
      void this.handleMessage(event.data);
    };
    const ready: BridgeControl = {
      protocol_version: PROTOCOL_VERSION,
      type: "bridge.ready",
      session_id: this.session.session_id,
      grant: { actions: [...this.session.grant.actions], read_views: [...this.session.grant.read_views] },
      expires_at: this.session.expires_at,
    };
    port.postMessage(ready);
    this.onEvent({ kind: "ready", detail: { session_id: this.session.session_id } });
  }

  /**
   * Create a channel, keep one end, transfer the other to the exact target window. The
   * target origin is "*" because a sandboxed srcdoc frame has an opaque origin; identity comes
   * from the transferred port, never from an origin string.
   */
  attachToWindow(target: Window, targetOrigin = "*"): void {
    const channel = new MessageChannel();
    const init: BridgeInit = {
      protocol_version: PROTOCOL_VERSION,
      type: "bridge.init",
      session_id: this.session.session_id,
    };
    this.bind(channel.port1);
    target.postMessage(init, targetOrigin, [channel.port2]);
  }

  /** End the session: tell the child, then close the port. Nothing is answered afterwards. */
  revoke(reason: string): void {
    if (this.revoked) return;
    this.revoked = true;
    if (this.port) {
      const notice: BridgeControl = {
        protocol_version: PROTOCOL_VERSION,
        type: "bridge.revoked",
        session_id: this.session.session_id,
        reason,
      };
      try {
        this.port.postMessage(notice);
      } catch {
        /* port may already be gone */
      }
      this.port.onmessage = null;
      this.port.close();
      this.port = null;
    }
    this.onEvent({ kind: "revoked", detail: { session_id: this.session.session_id, reason } });
  }

  private expired(): boolean {
    const expiry = Date.parse(this.session.expires_at);
    return Number.isFinite(expiry) && this.now() > expiry;
  }

  /** Public for tests; the port handler calls this. */
  async handleMessage(data: unknown): Promise<void> {
    if (this.revoked || !this.port) {
      this.onEvent({ kind: "dropped", detail: { reason: "revoked" } });
      return;
    }
    const validation = validateRequest(data, this.session.session_id);
    if (!validation.ok) {
      this.respondError(validation.request_id, validation.error);
      return;
    }
    const request = validation.request;
    if (this.expired()) {
      this.respondError(request.request_id, { code: "revoked", message: "session expired", recovery: "reload the workflow" });
      this.revoke("expired");
      return;
    }
    if (this.inFlight >= this.maxInFlight) {
      this.respondError(request.request_id, { code: "throttled", message: "too many requests in flight" });
      return;
    }
    this.inFlight += 1;
    this.onEvent({ kind: "request", detail: { request_id: request.request_id, type: request.type } });
    try {
      const data = await this.dispatch(request);
      this.respond({
        protocol_version: PROTOCOL_VERSION,
        session_id: this.session.session_id,
        request_id: request.request_id,
        type: "result",
        data,
      });
    } catch (error) {
      if (error instanceof BridgeError) {
        this.respondError(request.request_id, { code: error.code, message: error.message, recovery: error.recovery });
      } else {
        // Never leak handler internals to unprivileged UI.
        this.respondError(request.request_id, { code: "internal", message: "the request could not be completed" });
        this.onEvent({ kind: "error", detail: { request_id: request.request_id, internal: String(error) } });
      }
    } finally {
      this.inFlight -= 1;
    }
  }

  private async dispatch(request: BridgeRequest): Promise<unknown> {
    const { payload } = request;
    switch (request.type) {
      case "action.invoke": {
        const actionId = payload.action_id;
        if (typeof actionId !== "string" || !actionId || !isPlainObject(payload.input)) {
          throw new BridgeError("invalid_request", "action.invoke needs action_id and input object");
        }
        if (!this.session.grant.actions.includes(actionId)) {
          throw new BridgeError("forbidden", `action ${actionId} is not granted to this session`);
        }
        if (!this.handlers.actionInvoke) throw new BridgeError("unsupported", "actions are not available here");
        const result = await this.handlers.actionInvoke(this.session, { action_id: actionId, input: payload.input });
        this.operations.add(result.operation_id);
        return result;
      }
      case "operation.observe": {
        const operationId = payload.operation_id;
        const after = payload.after ?? 0;
        if (typeof operationId !== "string" || !operationId || typeof after !== "number" || after < 0) {
          throw new BridgeError("invalid_request", "operation.observe needs operation_id and a non-negative after");
        }
        if (!this.operations.has(operationId)) {
          throw new BridgeError("forbidden", "operation is not owned by this session");
        }
        if (!this.handlers.operationObserve) throw new BridgeError("unsupported", "operations cannot be observed here");
        return this.handlers.operationObserve(this.session, { operation_id: operationId, after });
      }
      case "records.query": {
        const view = payload.view;
        if (typeof view !== "string" || !view) throw new BridgeError("invalid_request", "records.query needs a view");
        if (!this.session.grant.read_views.includes(view)) {
          throw new BridgeError("forbidden", `view ${view} is not granted to this session`);
        }
        if (!this.handlers.recordsQuery) throw new BridgeError("unsupported", "records are not available here");
        for (const key of Object.keys(payload)) {
          if (!RECORDS_QUERY_KEYS.has(key)) throw new BridgeError("invalid_request", `records.query does not take ${key}`);
        }
        const query: RecordsQueryPayload = { view };
        if (payload.where !== undefined) {
          if (!isPlainObject(payload.where)) throw new BridgeError("invalid_request", "where must be a filter object");
          query.where = payload.where;
        }
        if (payload.order_by !== undefined) {
          const order = payload.order_by;
          if (
            !Array.isArray(order) ||
            order.length > 3 ||
            !order.every((k) => isPlainObject(k) && typeof k.field === "string" && (k.direction === "asc" || k.direction === "desc"))
          ) {
            throw new BridgeError("invalid_request", "order_by is a list of up to three {field, direction} keys");
          }
          query.order_by = order as RecordsQueryPayload["order_by"];
        }
        if (payload.limit !== undefined) {
          if (typeof payload.limit !== "number" || !Number.isInteger(payload.limit) || payload.limit < 1 || payload.limit > 1000) {
            throw new BridgeError("invalid_request", "limit must be a whole number from 1 to 1000");
          }
          query.limit = payload.limit;
        }
        if (payload.cursor !== undefined) {
          if (typeof payload.cursor !== "string" || payload.cursor.length > 512) throw new BridgeError("invalid_request", "cursor must be a string");
          query.cursor = payload.cursor;
        }
        return this.handlers.recordsQuery(this.session, query);
      }
      case "artifact.open":
        if (!this.handlers.artifactOpen) throw new BridgeError("unsupported", "artifacts are not available here");
        return this.handlers.artifactOpen(this.session, payload);
      case "input.select":
        if (!this.handlers.inputSelect) throw new BridgeError("unsupported", "input selection is not available here");
        return this.handlers.inputSelect(this.session, payload);
      case "shell.navigate":
        if (!this.handlers.shellNavigate) throw new BridgeError("unsupported", "navigation is not available here");
        return this.handlers.shellNavigate(this.session, payload);
    }
  }

  private respond(message: BridgeResponse): void {
    if (!this.port || this.revoked) return;
    this.port.postMessage(message);
    this.onEvent({ kind: "result", detail: { request_id: message.request_id } });
  }

  private respondError(requestId: string, error: BridgeErrorBody): void {
    if (!this.port || this.revoked) return;
    const message: BridgeResponse = {
      protocol_version: PROTOCOL_VERSION,
      session_id: this.session.session_id,
      request_id: requestId,
      type: "error",
      error,
    };
    this.port.postMessage(message);
    this.onEvent({ kind: "error", detail: { request_id: requestId, code: error.code, message: error.message } });
  }
}
