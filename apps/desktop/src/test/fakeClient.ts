import type { Run, RunEvent } from "@alpha/contracts";
import type { CoreClient, HealthInfo, StreamItem, SyntheticRunRequest } from "../core/client";

/** In-memory CoreClient that reproduces Core's observable state machine for shell tests. */
export class FakeCoreClient implements CoreClient {
  runs = new Map<string, Run>();
  items: StreamItem[] = [];
  listeners: ((item: StreamItem) => void)[] = [];
  private cursor = 0;
  private sequence = new Map<string, number>();
  failCreate = false;

  async health(): Promise<HealthInfo> {
    return {
      status: "ok",
      core_version: "0.1.0-test",
      contract_version: "0.2",
      core_instance_id: "test",
      python_version: "3.13.9 (test)",
      python_executable: "/runtime/venv/bin/python",
      data_dir: "/data",
      worker_profiles: ["synthetic"],
      active_runs: [],
    };
  }

  async listRuns(): Promise<Run[]> {
    return [...this.runs.values()];
  }

  async createRun(request: SyntheticRunRequest): Promise<Run> {
    if (this.failCreate) throw new Error("boom");
    const now = new Date().toISOString();
    const run: Run = {
      contract_version: "0.2",
      run_id: `run_${this.runs.size + 1}`,
      workspace_id: "ws_test",
      owner: { kind: "task", task_id: "t", task_revision_id: "t.r1", attempt_id: "a", plan_ref: "worker-profile:synthetic" },
      origin: "user",
      state: "queued",
      snapshot: { worker_profile: "synthetic", input_digest: `sha256:${"0".repeat(64)}`, limits: { timeout_seconds: 60 } },
      created_at: now,
      updated_at: now,
      started_at: null,
      finished_at: null,
      output: null,
      terminal_reason: null,
      retry_of: null,
      latest_sequence: 0,
    };
    this.runs.set(run.run_id, run);
    this.emit(run.run_id, "run.queued", { origin: "user", text: request.text, mode: request.mode });
    return run;
  }

  async cancelRun(runId: string): Promise<Run> {
    return this.transition(runId, "cancelled", "run.cancelled", "cancelled_by_user");
  }

  async events(runId: string): Promise<RunEvent[]> {
    return this.items.filter((i) => i.run.run_id === runId).map((i) => i.event);
  }

  async stream(after: number, onItem: (item: StreamItem) => void, signal: AbortSignal): Promise<void> {
    for (const item of this.items) if (item.cursor > after) onItem(item);
    this.listeners.push(onItem);
    await new Promise<void>((resolve) => signal.addEventListener("abort", () => resolve(), { once: true }));
  }

  // --- test controls -------------------------------------------------------------------

  start(runId: string): Run {
    return this.transition(runId, "running", "run.started", null);
  }

  progress(runId: string, step: number): void {
    this.emit(runId, "worker.progress", { stage: "step", step });
  }

  succeed(runId: string, output: Record<string, unknown>): Run {
    return this.transition(runId, "succeeded", "run.succeeded", null, output);
  }

  fail(runId: string, reason: string): Run {
    return this.transition(runId, "failed", "run.failed", reason);
  }

  private transition(runId: string, state: Run["state"], kind: string, reason: string | null, output?: Record<string, unknown>): Run {
    const previous = this.runs.get(runId);
    if (!previous) throw new Error("run_not_found");
    const run: Run = { ...previous, state, terminal_reason: reason, output: output ?? previous.output, updated_at: new Date().toISOString() };
    this.runs.set(runId, run);
    this.emit(runId, kind, {});
    return run;
  }

  private emit(runId: string, kind: string, payload: Record<string, unknown>): void {
    const run = this.runs.get(runId)!;
    const sequence = (this.sequence.get(runId) ?? 0) + 1;
    this.sequence.set(runId, sequence);
    const updated: Run = { ...run, latest_sequence: sequence };
    this.runs.set(runId, updated);
    const event: RunEvent = {
      contract_version: "0.2",
      event_id: `evt_${++this.cursor}`,
      run_id: runId,
      sequence,
      kind,
      occurred_at: new Date().toISOString(),
      payload_schema_version: "0.2",
      payload,
      step_key: null,
    };
    const item = { cursor: this.cursor, event, run: updated };
    this.items.push(item);
    for (const listener of this.listeners) listener(item);
  }
}
