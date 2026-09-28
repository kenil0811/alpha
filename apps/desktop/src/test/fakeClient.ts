import type { Run, RunEvent, SolutionBrief } from "@alpha/contracts";
import type {
  CapabilityEntry,
  Conversation,
  ConversationReply,
  CoreClient,
  HealthInfo,
  ModelConnection,
  SettingField,
  BrowserSite,
  BrowserAccess,
  BrowserVisit,
  StreamItem,
  SyntheticRunRequest,
} from "../core/client";

/** In-memory CoreClient that reproduces Core's observable state machine for shell tests. */
export class FakeCoreClient implements CoreClient {
  runs = new Map<string, Run>();
  items: StreamItem[] = [];
  listeners: ((item: StreamItem) => void)[] = [];
  private cursor = 0;
  private sequence = new Map<string, number>();
  failCreate = false;
  conversations = new Map<string, Conversation>();
  /** Scripted assistant: called on start and on every reply; returns the next conversation state. */
  assistantScript: ((conversation: Conversation, reply: ConversationReply | null) => Conversation) | null = null;
  /** Simulate Core dispatching faster than the HTTP response returns: these run before
   *  createRun resolves. */
  beforeCreateResolves: ((runId: string) => void) | null = null;

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
    if (this.beforeCreateResolves) {
      this.beforeCreateResolves(run.run_id);
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
    return run;
  }

  async run(runId: string): Promise<Run> {
    const run = this.runs.get(runId);
    if (!run) throw new Error("run_not_found");
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

  async startConversation(text: string, changeOf?: string | null): Promise<Conversation> {
    const now = new Date().toISOString();
    let conversation: Conversation = {
      conversation_id: `conv_${this.conversations.size + 1}`,
      change_of: changeOf ?? null,
      state: "thinking",
      route_id: "fake",
      created_at: now,
      updated_at: now,
      turns: [{ turn_id: "t1", sequence: 1, role: "user", kind: "request", content: { text }, created_at: now }],
      current_brief: null,
      interpretation: null,
      questions: [],
      reply: null,
      delivery: null,
      error: null,
    };
    if (this.assistantScript) conversation = this.assistantScript(conversation, null);
    this.conversations.set(conversation.conversation_id, conversation);
    return conversation;
  }

  async conversation(id: string): Promise<Conversation> {
    const c = this.conversations.get(id);
    if (!c) throw new Error("conversation_not_found");
    return c;
  }

  /** What Settings -> Models reports; null means this host does not answer (older Core). */
  connection: ModelConnection | null = fakeConnection("connected");
  connectionChecks = 0;
  signIns = 0;
  async modelConnection(): Promise<ModelConnection> {
    if (!this.connection) throw new Error("not found");
    return this.connection;
  }
  async checkModelConnection(): Promise<ModelConnection> {
    this.connectionChecks += 1;
    return { ...(await this.modelConnection()), check: { ok: this.connection?.status === "connected", elapsed_ms: 900 } };
  }
  async signInToClaude(): Promise<ModelConnection> {
    this.signIns += 1;
    this.connection = { ...(await this.modelConnection()), login: { state: "waiting", started_at: new Date().toISOString() } };
    return this.connection;
  }

  settingsFields: SettingField[] = [
    { id: "models.assistant", group: "Models", title: "Model for the assistant", description: "Understands your request.", kind: "choice", options: [{ value: "default", label: "Claude Code's default" }, { value: "sonnet", label: "Claude Sonnet (faster)" }], minimum: null, maximum: null, unit: null, default: "default", value: "default" },
    { id: "models.builder_new", group: "Models", title: "Model for building a new module", description: "Writes the module.", kind: "choice", options: [{ value: "default", label: "Claude Code's default" }, { value: "sonnet", label: "Claude Sonnet (faster)" }], minimum: null, maximum: null, unit: null, default: "default", value: "default" },
    { id: "effort.planner", group: "Models", title: "Thinking for the checks", description: "How long the model thinks.", kind: "choice", options: [{ value: "low", label: "Low (fastest)" }, { value: "medium", label: "Medium" }, { value: "high", label: "High (slowest)" }, { value: "default", label: "Claude Code's default" }], minimum: null, maximum: null, unit: null, default: "low", value: "low" },
    { id: "build.max_attempt_minutes", group: "Building limits", title: "Minutes per attempt", description: "An attempt that runs longer is stopped.", kind: "integer", options: [], minimum: 3, maximum: 40, unit: "min", default: 15, value: 15 },
  ];
  settingsUpdates: Record<string, unknown>[] = [];

  sites: BrowserSite[] = [];
  browserAvailable = true;
  access = new Map<string, string[]>();
  visitsByApp = new Map<string, BrowserVisit[]>();
  async browserSites(): Promise<{ available: boolean; sites: BrowserSite[] }> {
    return { available: this.browserAvailable, sites: this.sites };
  }
  async connectBrowserSite(site: string): Promise<{ site: string; state: string }> {
    const key = site.toLowerCase().replace(/^https?:\/\//, "").replace(/^www\./, "").split("/")[0];
    this.sites = [...this.sites.filter((s) => s.site !== key), { site: key, state: "signing_in", connected_at: null, last_error: null, apps: [] }];
    return { site: key, state: "signing_in" };
  }
  async removeBrowserSite(site: string): Promise<void> {
    this.sites = this.sites.filter((s) => s.site !== site);
  }
  async browserAccess(appId: string): Promise<BrowserAccess[]> {
    const allowed = new Set(this.access.get(appId) ?? []);
    return this.sites.map((s) => ({ site: s.site, state: s.state, allowed: allowed.has(s.site) }));
  }
  async setBrowserAccess(appId: string, sites: string[]): Promise<BrowserAccess[]> {
    this.access.set(appId, sites);
    return this.browserAccess(appId);
  }
  async browserVisits(appId: string): Promise<BrowserVisit[]> {
    return this.visitsByApp.get(appId) ?? [];
  }

  async getSettings(): Promise<SettingField[]> {
    return this.settingsFields;
  }

  async updateSettings(values: Record<string, unknown>): Promise<SettingField[]> {
    this.settingsUpdates.push(values);
    this.settingsFields = this.settingsFields.map((f) => (f.id in values ? { ...f, value: values[f.id] } : f));
    return this.settingsFields;
  }

  async appConversations(appId: string): Promise<Conversation[]> {
    return [...this.conversations.values()].filter((c) => c.change_of === appId).reverse();
  }

  cancelled: string[] = [];
  async cancelConversation(id: string): Promise<Conversation> {
    const c = await this.conversation(id);
    this.cancelled.push(id);
    const stopped: Conversation = { ...c, state: "failed", error: "You stopped it" };
    this.conversations.set(id, stopped);
    return stopped;
  }

  async listConversations(): Promise<Conversation[]> {
    return [...this.conversations.values()];
  }

  async replyConversation(id: string, reply: ConversationReply): Promise<Conversation> {
    let c = await this.conversation(id);
    c = { ...c, turns: [...c.turns, { turn_id: `t${c.turns.length + 1}`, sequence: c.turns.length + 1, role: "user", kind: "answer", content: { ...reply }, created_at: new Date().toISOString() }] };
    if (this.assistantScript) c = this.assistantScript(c, reply);
    this.conversations.set(id, c);
    return c;
  }

  /** Test control: how the retried turn ends (defaults to running the script again). */
  retryScript: ((conversation: Conversation) => Conversation) | null = null;
  retries = 0;

  async retryConversation(id: string): Promise<Conversation> {
    let c = await this.conversation(id);
    if (c.state !== "failed") throw new Error("only a failed turn can be retried");
    this.retries += 1;
    c = { ...c, state: "thinking", error: null };
    if (this.retryScript) c = this.retryScript(c);
    else if (this.assistantScript) c = this.assistantScript(c, null);
    this.conversations.set(id, c);
    return c;
  }

  async capabilities(): Promise<CapabilityEntry[]> {
    return [{ family: "compute", description: "calculations", available: true, unavailable_reason: null, arrives_with: null }];
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

export function sampleBrief(overrides: Partial<SolutionBrief> = {}): SolutionBrief {
  return {
    contract_version: "0.2",
    id: "brief_1",
    revision: 1,
    conversation_id: "conv_1",
    created_at: new Date().toISOString(),
    goal: "Track what I eat and how much, with calories, history and trends",
    success_summary: "Entries take seconds and today's total is always right.",
    delivery: "app",
    surfaces: ["custom_ui"],
    inputs: [],
    primary_journey: [{ action: "Type a food and how much", expected_result: "An entry with an estimate appears" }],
    data_needs: [
      {
        collection: "food_entries",
        purpose: "Everything eaten",
        fields: [
          { name: "food", kind: "text", description: "What was eaten", required: true },
          { name: "calories", kind: "number", description: "Estimate", required: true },
        ],
        provenance: "user",
        retention: "until deleted",
      },
    ],
    actions: [],
    recurrence: null,
    constraints: [],
    acceptance_examples: [],
    assumptions: [
      { text: "Single user on this Mac", source: "model_default", turn_ref: null },
      { text: "Portions entered as rough sizes", source: "user_answer", turn_ref: "t2" },
    ],
    open_questions: [],
    unavailable_capabilities: ["records"],
    selected_context_snapshot_id: "conv_1.context.r1",
    supersedes_revision: null,
    ...overrides,
  };
}

/** A connection report as Core gives it, for one status. */
export function fakeConnection(status: ModelConnection["status"], overrides: Partial<ModelConnection> = {}): ModelConnection {
  const fixes: Partial<Record<ModelConnection["status"], string>> = {
    signed_out: "Sign in to Claude Code: press Sign in, or run `claude auth login` in Terminal.",
    cli_missing: "Install Claude Code (https://claude.com/claude-code), sign in once, then press Check now.",
    cli_too_old: "Update Claude Code: run `claude update` in Terminal, then press Check now.",
    last_call_failed: "Press Check now to try a small call. If it keeps failing, see the reason above.",
  };
  return {
    route_enabled: status !== "not_used",
    status,
    fix: fixes[status] ?? null,
    cli_found: status !== "cli_missing",
    cli_path: status === "cli_missing" ? null : "/opt/homebrew/bin/claude",
    cli_version: status === "cli_missing" ? null : status === "cli_too_old" ? "2.1.223" : "2.1.283",
    min_supported_version: "2.1.283",
    version_supported: status !== "cli_too_old" && status !== "cli_missing",
    missing_flags: status === "cli_too_old" ? ["--permission-prompts", "--restricted"] : [],
    logged_in: status === "signed_out" ? false : status === "connected" || status === "last_call_failed" ? true : null,
    account: status === "connected" || status === "last_call_failed" ? { auth_method: "claude.ai", email: "person@example.com", organization: "Person", plan: "max" } : null,
    last_successful_call_at: status === "connected" ? new Date(Date.now() - 120_000).toISOString() : null,
    last_call_latency_ms: status === "connected" ? 7400 : null,
    last_error: status === "last_call_failed" ? { code: "timeout", message: "model call exceeded 300s", at: new Date().toISOString() } : null,
    login: null,
    checked_at: new Date().toISOString(),
    ...overrides,
  };
}
