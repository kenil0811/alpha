import type { Run, RunEvent } from "@alpha/contracts";

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
}

export class CoreError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
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

export class HttpCoreClient implements CoreClient {
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
      try {
        const body = (await response.json()) as { detail?: string; error?: string };
        detail = body.detail ?? body.error ?? detail;
      } catch {
        /* keep statusText */
      }
      throw new CoreError(detail, response.status);
    }
    return (await response.json()) as T;
  }

  health(): Promise<HealthInfo> {
    return this.request<HealthInfo>("/api/health");
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
