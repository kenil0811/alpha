import type { Run, RunEvent, SolutionBrief } from "@alpha/contracts";

export interface CoreSession {
  baseUrl: string;
  token: string;
}

export interface SyntheticRunRequest {
  text: string;
  mode?: "succeed" | "fail" | "hang" | "crash" | "exit_without_result";
  steps?: number;
  delay_seconds?: number;
  spawn_child?: boolean;
  timeout_seconds?: number;
}

export interface HealthInfo {
  status: string;
  core_version: string;
  contract_version: string;
  core_instance_id: string;
  python_version: string;
  python_executable: string;
  data_dir: string;
  worker_profiles: string[];
  active_runs: string[];
}

export interface OpenQuestion {
  id: string;
  question: string;
  options: string[];
  why_it_matters: string;
}

export interface Interpretation {
  outcome: string;
  main_input: string;
  useful_result: string;
  important_assumptions: string[];
}

export interface ConversationTurn {
  turn_id: string;
  sequence: number;
  role: "user" | "assistant";
  kind: string;
  content: Record<string, unknown>;
  created_at: string;
}

export type ConversationState = "thinking" | "waiting_for_user" | "briefed" | "answered" | "failed";

export interface Conversation {
  conversation_id: string;
  state: ConversationState;
  route_id: string;
  created_at: string;
  updated_at: string;
  turns: ConversationTurn[];
  current_brief: SolutionBrief | null;
  interpretation: Interpretation | null;
  questions: OpenQuestion[];
  reply: string | null;
  delivery: "answer" | "task" | "app" | null;
  error: string | null;
}

export interface ConversationReply {
  text?: string;
  answers?: Record<string, string>;
  use_defaults?: boolean;
}

export interface CapabilityEntry {
  family: string;
  description: string;
  available: boolean;
  unavailable_reason: string | null;
  arrives_with: string | null;
}

export interface StreamItem {
  cursor: number;
  event: RunEvent;
  run: Run;
}

export interface CoreClient {
  health(): Promise<HealthInfo>;
  listRuns(): Promise<Run[]>;
  createRun(request: SyntheticRunRequest): Promise<Run>;
  run(runId: string): Promise<Run>;
  cancelRun(runId: string): Promise<Run>;
  events(runId: string): Promise<RunEvent[]>;
  stream(after: number, onItem: (item: StreamItem) => void, signal: AbortSignal): Promise<void>;
  startConversation(text: string): Promise<Conversation>;
  conversation(id: string): Promise<Conversation>;
  listConversations(): Promise<Conversation[]>;
  replyConversation(id: string, reply: ConversationReply): Promise<Conversation>;
  capabilities(): Promise<CapabilityEntry[]>;
}

export class CoreError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    /** Capability failure code from Core ("invalid_input", "forbidden", …) when it sent one. */
    public readonly code?: string,
  ) {
    super(message);
  }
}

export interface ViewSpec {
  id: string;
  kind: "records" | "aggregate";
  collection: string;
  description?: string;
}

export interface AppDetail {
  app_id: string;
  name: string;
  description: string;
  version_id: string;
  release_id: string;
  package_sha256: string;
  runtime_profile_id: string;
  ui: { views: ViewSpec[]; actions: string[] } | null;
}

export interface OperationOutcome {
  operation_id: string;
  state: string;
  output: Record<string, unknown> | null;
  error: { code: string; message: string } | null;
}

/** Installed-App commands used by the shell's bridge host (F05/F06 routes). */
export interface AppsClient {
  appDetail(appId: string): Promise<AppDetail>;
  installFixtureApp(name: string): Promise<{ app_id: string }>;
  runAppAction(appId: string, actionId: string, input: Record<string, unknown>): Promise<Run>;
  queryView(appId: string, viewId: string, body: Record<string, unknown>): Promise<unknown>;
  operationOutcome(runId: string): Promise<OperationOutcome>;
}

export function isAppsClient(client: unknown): client is AppsClient {
  return typeof (client as Partial<AppsClient>)?.queryView === "function";
}

/** The plain-language failure of a finished run, from its events. */
export function outcomeFromEvents(run: Run, events: RunEvent[]): OperationOutcome {
  let error: OperationOutcome["error"] = null;
  if (run.state !== "succeeded") {
    const workerError = [...events].reverse().find((e) => e.kind === "worker.error");
    const failed = [...events].reverse().find((e) => e.kind === "run.failed");
    const payload = (workerError?.payload ?? {}) as Record<string, unknown>;
    const failure = (failed?.payload ?? {}) as Record<string, unknown>;
    const message =
      (typeof payload.message === "string" && payload.message) ||
      (typeof failure.problem === "string" && `The result did not match what the action promises: ${failure.problem}`) ||
      run.terminal_reason ||
      `The action ${run.state}.`;
    const code = (typeof payload.operation_code === "string" && payload.operation_code) || run.terminal_reason || run.state;
    error = { code, message };
  }
  return { operation_id: run.run_id, state: run.state, output: (run.output as Record<string, unknown> | null) ?? null, error };
}

/** Parse one or more SSE frames from a text chunk. Returns leftover text. */
export function parseSseChunk(
  buffer: string,
  emit: (frame: { id?: string; event?: string; data: string }) => void,
): string {
  let rest = buffer;
  for (;;) {
    const boundary = rest.indexOf("\n\n");
    if (boundary === -1) return rest;
    const frame = rest.slice(0, boundary);
    rest = rest.slice(boundary + 2);
    let id: string | undefined;
    let event: string | undefined;
    const data: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith(":")) continue;
      const sep = line.indexOf(":");
      const field = sep === -1 ? line : line.slice(0, sep);
      const value = sep === -1 ? "" : line.slice(sep + 1).replace(/^ /, "");
      if (field === "id") id = value;
      else if (field === "event") event = value;
      else if (field === "data") data.push(value);
    }
    if (data.length) emit({ id, event, data: data.join("\n") });
  }
}

export class HttpCoreClient implements CoreClient, AppsClient {
  constructor(
    private readonly session: CoreSession,
    private readonly fetchImpl: typeof fetch = (...args) => fetch(...args),
  ) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.fetchImpl(`${this.session.baseUrl}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${this.session.token}`,
        "Content-Type": "application/json",
        ...(init.headers ?? {}),
      },
    });
    if (!response.ok) {
      let detail = response.statusText;
      let code: string | undefined;
      try {
        const body = (await response.json()) as { detail?: unknown; error?: string };
        if (typeof body.detail === "string") detail = body.detail;
        else if (body.detail && typeof body.detail === "object" && !Array.isArray(body.detail)) {
          const structured = body.detail as { code?: unknown; message?: unknown };
          if (typeof structured.message === "string") detail = structured.message;
          if (typeof structured.code === "string") code = structured.code;
        } else if (Array.isArray(body.detail)) {
          detail = "The request was not valid.";
          code = "invalid_input";
        } else if (body.error) detail = body.error;
      } catch {
        /* keep statusText */
      }
      throw new CoreError(detail, response.status, code);
    }
    return (await response.json()) as T;
  }

  health(): Promise<HealthInfo> {
    return this.request<HealthInfo>("/api/health");
  }

  appDetail(appId: string): Promise<AppDetail> {
    return this.request<AppDetail>(`/api/apps/${encodeURIComponent(appId)}`);
  }

  installFixtureApp(name: string): Promise<{ app_id: string }> {
    return this.request(`/api/dev/fixture-apps/${encodeURIComponent(name)}/install`, { method: "POST" });
  }

  runAppAction(appId: string, actionId: string, input: Record<string, unknown>): Promise<Run> {
    return this.request<Run>(`/api/apps/${encodeURIComponent(appId)}/actions/${encodeURIComponent(actionId)}/runs`, {
      method: "POST",
      body: JSON.stringify({ input, origin: "ui" }),
    });
  }

  queryView(appId: string, viewId: string, body: Record<string, unknown>): Promise<unknown> {
    return this.request(`/api/apps/${encodeURIComponent(appId)}/views/${encodeURIComponent(viewId)}/query`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async operationOutcome(runId: string): Promise<OperationOutcome> {
    const run = await this.run(runId);
    if (!["succeeded", "failed", "cancelled", "interrupted"].includes(run.state)) {
      return { operation_id: run.run_id, state: run.state, output: null, error: null };
    }
    return outcomeFromEvents(run, run.state === "succeeded" ? [] : await this.events(runId));
  }

  async listRuns(): Promise<Run[]> {
    const page = await this.request<{ runs: Run[] }>("/api/runs?limit=50");
    return page.runs;
  }

  createRun(request: SyntheticRunRequest): Promise<Run> {
    return this.request<Run>("/api/runs", { method: "POST", body: JSON.stringify(request) });
  }

  run(runId: string): Promise<Run> {
    return this.request<Run>(`/api/runs/${encodeURIComponent(runId)}`);
  }

  cancelRun(runId: string): Promise<Run> {
    return this.request<Run>(`/api/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" });
  }

  async events(runId: string): Promise<RunEvent[]> {
    const page = await this.request<{ events: RunEvent[] }>(
      `/api/runs/${encodeURIComponent(runId)}/events`,
    );
    return page.events;
  }

  startConversation(text: string): Promise<Conversation> {
    return this.request<Conversation>("/api/conversations", { method: "POST", body: JSON.stringify({ text }) });
  }

  conversation(id: string): Promise<Conversation> {
    return this.request<Conversation>(`/api/conversations/${encodeURIComponent(id)}`);
  }

  async listConversations(): Promise<Conversation[]> {
    const page = await this.request<{ conversations: Conversation[] }>("/api/conversations?limit=20");
    return page.conversations;
  }

  replyConversation(id: string, reply: ConversationReply): Promise<Conversation> {
    return this.request<Conversation>(`/api/conversations/${encodeURIComponent(id)}/messages`, {
      method: "POST",
      body: JSON.stringify(reply),
    });
  }

  async capabilities(): Promise<CapabilityEntry[]> {
    const page = await this.request<{ capabilities: CapabilityEntry[] }>("/api/capabilities");
    return page.capabilities;
  }

  async stream(after: number, onItem: (item: StreamItem) => void, signal: AbortSignal): Promise<void> {
    const response = await this.fetchImpl(`${this.session.baseUrl}/api/events/stream?after=${after}`, {
      headers: { Authorization: `Bearer ${this.session.token}` },
      signal,
    });
    if (!response.ok || !response.body) throw new CoreError("stream unavailable", response.status);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      buffer = parseSseChunk(buffer, (frame) => {
        if (frame.event !== "run_event") return;
        const body = JSON.parse(frame.data) as { event: RunEvent; run: Run };
        onItem({ cursor: Number(frame.id ?? 0), event: body.event, run: body.run });
      });
    }
  }
}
