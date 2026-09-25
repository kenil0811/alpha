/**
 * BridgeClient: the generated UI's end. It accepts a port only from the exact parent window
 * (event.source === window.parent), never from an origin string, and exposes typed requests.
 * It has no way to reach the shell, Core, native APIs or another session: it holds one port.
 */

import {
  PROTOCOL_VERSION,
  type BridgeControl,
  type BridgeErrorBody,
  type BridgeGrant,
  type BridgeHello,
  type BridgeRequest,
  type BridgeResponse,
  type RequestType,
} from "./protocol";

export class BridgeRequestError extends Error {
  constructor(
    public readonly code: BridgeErrorBody["code"],
    message: string,
    public readonly recovery?: string,
  ) {
    super(message);
  }
}

interface Pending {
  resolve: (value: unknown) => void;
  reject: (error: BridgeRequestError) => void;
  timer: ReturnType<typeof setTimeout>;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export class BridgeClient {
  readonly sessionId: string;
  private readonly port: MessagePort;
  private readonly pending = new Map<string, Pending>();
  private readonly revokedListeners = new Set<(reason: string) => void>();
  private grantValue: BridgeGrant | null = null;
  private expiresAt: string | null = null;
  private revokedReason: string | null = null;
  private counter = 0;
  private readyResolve: (() => void) | null = null;
  private readonly ready: Promise<void>;

  private constructor(port: MessagePort, sessionId: string) {
    this.port = port;
    this.sessionId = sessionId;
    this.ready = new Promise<void>((resolve) => {
      this.readyResolve = resolve;
    });
    port.onmessage = (event: MessageEvent) => this.handle(event.data);
  }

  /** Bind to a port handed over by the exact parent window. */
  static fromPort(port: MessagePort, sessionId: string): BridgeClient {
    return new BridgeClient(port, sessionId);
  }

  /**
   * Wait for the parent's bridge.init handshake. Only a message whose source is the parent
   * window and which transfers exactly one port is accepted; anything else is ignored.
   */
  static connect(options: { parent?: Window; timeoutMs?: number } = {}): Promise<BridgeClient> {
    const parent = options.parent ?? window.parent;
    const timeoutMs = options.timeoutMs ?? 10_000;
    return new Promise<BridgeClient>((resolve, reject) => {
      const timer = setTimeout(() => {
        window.removeEventListener("message", listener);
        reject(new BridgeRequestError("revoked", "no bridge handshake from the host"));
      }, timeoutMs);
      const listener = (event: MessageEvent) => {
        if (event.source !== parent) return;
        const data: unknown = event.data;
        if (!isPlainObject(data) || data.type !== "bridge.init" || data.protocol_version !== PROTOCOL_VERSION) return;
        if (typeof data.session_id !== "string" || event.ports.length !== 1) return;
        clearTimeout(timer);
        window.removeEventListener("message", listener);
        const client = new BridgeClient(event.ports[0], data.session_id);
        client.ready.then(() => resolve(client));
      };
      window.addEventListener("message", listener);
      // Announce readiness; the host attaches a port only after this, so no init is lost to
      // the race between frame load and the client's listener registration.
      const hello: BridgeHello = { protocol_version: PROTOCOL_VERSION, type: "bridge.hello" };
      parent.postMessage(hello, "*");
    });
  }

  get grant(): BridgeGrant | null {
    return this.grantValue;
  }

  get expires(): string | null {
    return this.expiresAt;
  }

  get revoked(): string | null {
    return this.revokedReason;
  }

  whenReady(): Promise<void> {
    return this.ready;
  }

  onRevoked(listener: (reason: string) => void): () => void {
    this.revokedListeners.add(listener);
    return () => this.revokedListeners.delete(listener);
  }

  request<T = unknown>(type: RequestType, payload: Record<string, unknown>, timeoutMs = 30_000): Promise<T> {
    if (this.revokedReason !== null) {
      return Promise.reject(new BridgeRequestError("revoked", `session revoked: ${this.revokedReason}`));
    }
    const requestId = `req_${++this.counter}_${Math.random().toString(36).slice(2, 10)}`;
    const message: BridgeRequest = {
      protocol_version: PROTOCOL_VERSION,
      session_id: this.sessionId,
      request_id: requestId,
      type,
      payload,
    };
    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(requestId);
        reject(new BridgeRequestError("internal", "the host did not answer in time"));
      }, timeoutMs);
      this.pending.set(requestId, { resolve: resolve as (value: unknown) => void, reject, timer });
      this.port.postMessage(message);
    });
  }

  close(): void {
    this.port.onmessage = null;
    this.port.close();
  }

  private handle(data: unknown): void {
    if (!isPlainObject(data) || data.protocol_version !== PROTOCOL_VERSION) return;
    if (data.session_id !== this.sessionId) return;
    if (data.type === "bridge.ready") {
      const control = data as unknown as Extract<BridgeControl, { type: "bridge.ready" }>;
      this.grantValue = control.grant;
      this.expiresAt = control.expires_at;
      this.readyResolve?.();
      return;
    }
    if (data.type === "bridge.revoked") {
      const control = data as unknown as Extract<BridgeControl, { type: "bridge.revoked" }>;
      this.revokedReason = control.reason;
      for (const [id, entry] of this.pending) {
        clearTimeout(entry.timer);
        entry.reject(new BridgeRequestError("revoked", `session revoked: ${control.reason}`));
        this.pending.delete(id);
      }
      for (const listener of this.revokedListeners) listener(control.reason);
      return;
    }
    if (data.type !== "result" && data.type !== "error") return;
    const response = data as unknown as BridgeResponse;
    const entry = this.pending.get(response.request_id);
    if (!entry) return;
    clearTimeout(entry.timer);
    this.pending.delete(response.request_id);
    if (response.type === "result") entry.resolve(response.data);
    else entry.reject(new BridgeRequestError(response.error.code, response.error.message, response.error.recovery));
  }
}
