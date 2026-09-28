import type { Run, RunEvent, SolutionBrief } from "@alpha/contracts";

/**
 * The declarative screen and its declared views, as Core returns them (contract app_source with
 * every default filled in). Written out here so the shell has plain arrays, not the generated
 * schema's tuple types.
 */
export type FilterNode = { field: string; op: string; value?: unknown } | { all: FilterNode[] } | { any: FilterNode[] } | { not: FilterNode };
export interface DeclaredView {
  id: string;
  kind: "records" | "aggregate";
  collection: string;
  description?: string;
  where: FilterNode | null;
  fields: string[] | null;
  filterable: string[];
  sortable: string[];
  default_order: { field: string; direction: "asc" | "desc" }[];
  max_limit: number;
  group_by: { field: string; bucket: "day" | "week" | "month" | null; timezone?: string | null }[];
  metrics: { name: string; fn: string; field: string | null }[];
}
export interface ActionBinding {
  action: string;
  id_param?: string | null;
  input: Record<string, unknown>;
  title?: string | null;
  confirm?: string | null;
}
export interface SavedList {
  id: string;
  title: string;
  where: FilterNode | null;
}
export interface ScreenColumn {
  field: string;
  title?: string | null;
  format?: "text" | "number" | "date" | "datetime" | "pill" | "link" | "check" | null;
  unit?: string | null;
  editable: boolean;
  width?: "narrow" | "normal" | "wide" | null;
}
export interface QuickEntryBlock {
  kind: "quick_entry";
  action: string;
  input: string;
  placeholder: string;
  voice: boolean;
  extra: Record<string, unknown>;
}
export interface DetailSpec {
  title_field?: string | null;
  fields: string[];
  long_fields: string[];
  actions: ActionBinding[];
}
export interface TableBlock {
  kind: "table";
  view: string;
  title?: string | null;
  columns: ScreenColumn[];
  lists: SavedList[];
  /** Click a row to open the record's own page. */
  detail?: DetailSpec | null;
  edit: ActionBinding | null;
  delete: ActionBinding | null;
  row_actions: ActionBinding[];
  totals: string[];
  empty?: string | null;
  page_size: number;
}
export interface GoalFrom {
  view: string;
  field: string;
}
export interface MetricCardSpec {
  title: string;
  view: string;
  metric: string;
  unit?: string | null;
  goal?: number | null;
  goal_from?: GoalFrom | null;
  goal_label?: string | null;
  hint?: string | null;
}
export interface MetricsBlock {
  kind: "metrics";
  title?: string | null;
  cards: MetricCardSpec[];
}
export interface TrendBlock {
  kind: "trend";
  title: string;
  view: string;
  x: string;
  y: string;
  unit?: string | null;
  goal?: number | null;
  goal_from?: GoalFrom | null;
  days: number;
}
export interface BoardBlock {
  kind: "board";
  view: string;
  title?: string | null;
  group_field: string;
  columns: string[];
  title_field: string;
  subtitle_fields: string[];
  badge_field?: string | null;
  move: ActionBinding | null;
  field_param?: string | null;
  card_actions: ActionBinding[];
}
export interface ListBlock {
  kind: "list";
  view: string;
  title?: string | null;
  title_field: string;
  subtitle_fields: string[];
  badge_field?: string | null;
  link_field?: string | null;
  item_actions: ActionBinding[];
  empty?: string | null;
}
export interface FormBlock {
  kind: "form";
  action: string;
  title?: string | null;
  description?: string | null;
  submit_label?: string | null;
  prefill_view?: string | null;
}
export interface TextBlock {
  kind: "text";
  title?: string | null;
  body: string;
}
export interface ProgressBlock extends MetricCardSpec {
  kind: "progress";
}
export type ScreenBlock = QuickEntryBlock | TableBlock | MetricsBlock | TrendBlock | BoardBlock | ListBlock | FormBlock | TextBlock | ProgressBlock;
export interface ScreenTab {
  id: string;
  title: string;
  blocks: ScreenBlock[];
}
export interface Screen {
  icon?: string | null;
  tabs: ScreenTab[];
  assistant_hint?: string | null;
}

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

/** A setting the person may change, as Core describes it. */
export interface SettingField {
  id: string;
  group: string;
  title: string;
  description: string;
  kind: "choice" | "integer" | "text";
  options: { value: string; label: string }[];
  minimum: number | null;
  maximum: number | null;
  unit: string | null;
  default: unknown;
  value: unknown;
}

/** A site the person signed into in Alpha's own browser. */
export interface BrowserSite {
  site: string;
  state: "signing_in" | "connected" | "not_connected";
  connected_at: string | null;
  last_error: string | null;
  apps: string[];
}
export interface BrowserAccess {
  site: string;
  state: BrowserSite["state"];
  allowed: boolean;
}
export interface BrowserVisit {
  visit_id: string;
  app_id: string;
  run_id: string | null;
  site: string;
  url: string;
  final_url: string | null;
  status: number | null;
  blocked: number;
  signed_in: number;
  at: string;
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
  /** Where this conversation's data goes, stated by Core from the configured routes. */
  data_notice?: string | null;
  /** The module this conversation changes (rebuilt in place, data kept); null for a new one. */
  change_of?: string | null;
  /** A small change Alpha makes directly (no plan); its creation starts on its own. */
  quick_change?: boolean;
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
  /** Begin a request: about something new, or (changeOf) about changing an existing module. */
  startConversation(text: string, changeOf?: string | null): Promise<Conversation>;
  conversation(id: string): Promise<Conversation>;
  listConversations(): Promise<Conversation[]>;
  /** Settings the person may change (models per stage, build limits) with current values. */
  /** The signed-in browser: sites connected, what a module may read through them, pages opened. */
  browserSites(): Promise<{ available: boolean; sites: BrowserSite[] }>;
  connectBrowserSite(site: string): Promise<{ site: string; state: string }>;
  removeBrowserSite(site: string): Promise<void>;
  browserAccess(appId: string): Promise<BrowserAccess[]>;
  setBrowserAccess(appId: string, sites: string[]): Promise<BrowserAccess[]>;
  browserVisits(appId: string): Promise<BrowserVisit[]>;
  getSettings(): Promise<SettingField[]>;
  updateSettings(values: Record<string, unknown>): Promise<SettingField[]>;
  /** A module's own thread: the request that made it and every change since, newest first. */
  appConversations(appId: string): Promise<Conversation[]>;
  replyConversation(id: string, reply: ConversationReply): Promise<Conversation>;
  /** Run a failed assistant turn again from the same input. */
  retryConversation(id: string): Promise<Conversation>;
  /** Stop a turn that is still thinking. */
  cancelConversation(id: string): Promise<Conversation>;
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
  ui: { entry?: string | null; views: ViewSpec[]; actions: string[] } | null;
  /** Top-level declared views (shared by the declarative screen and any custom ui). */
  views?: DeclaredView[];
  /** The declarative screen Alpha draws itself, when the module has one. */
  screen?: Screen | null;
  /** Summary cards the builder chose, drawn on the Summary tab above the derived pages. */
  summary?: ScreenBlock[];
  has_screen?: boolean;
  /** An earlier version is installed, so "go back" is possible. */
  can_revert?: boolean;
  capabilities?: string[];
  actions: ActionSummary[];
  collections: CollectionSummary[];
  record_counts: Record<string, number>;
  /** Where this App's data goes, stated by Core from the configured routes. */
  data_notice?: string;
  /** The one action a person runs to get this App's result (Apps without their own screen). */
  primary_action?: string | null;
}

export interface JsonSchema {
  type?: string | string[];
  title?: string;
  description?: string;
  /** What the action assumes when the input is left out. */
  default?: unknown;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  enum?: unknown[];
  items?: JsonSchema;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  /** Presentation hint from the App: show this text input as a multi-line box. */
  multiline?: boolean;
}

export interface ActionSummary {
  id: string;
  title: string;
  description: string;
  input_schema: JsonSchema;
  output_schema: JsonSchema;
  invocable_from: string[];
  effect_class: string;
}

export interface CollectionSummary {
  name: string;
  description?: string;
  fields: { name: string; kind: string; required?: boolean; description?: string; choices?: string[] | null; done_choices?: string[] | null }[];
  /** The field that names a record. */
  title_field?: string | null;
  /** How the derived page opens; every collection has one even without this. */
  page?: {
    view?: "table" | "board" | "list" | "calendar" | "chart";
    group_field?: string | null;
    date_field?: string | null;
    sort?: { field: string; direction: "asc" | "desc" } | null;
    columns?: string[] | null;
    quick_entry?: { action: string; input: string; placeholder: string } | null;
  } | null;
}

export interface ScheduleStatus {
  id: string;
  title: string;
  action: string;
  /** Plain words: "every 2 hours", "every day at 21:00". */
  when: string;
  enabled: boolean;
  last_run_at: string | null;
  last_run_id: string | null;
  last_error: string | null;
  next_run_at: string | null;
}

export interface RecordPageResult {
  records: RecordRow[];
  next_cursor: string | null;
}

export interface AggregateGroupResult {
  key: Record<string, unknown>;
  values: Record<string, number | string | null>;
}

export interface AggregateResultPage {
  groups: AggregateGroupResult[];
  truncated: boolean;
}

export interface AppSummary {
  app_id: string;
  name: string;
  description: string;
  origin: "created" | "fixture" | "build";
  state: string;
  has_ui: boolean;
  actions: number;
  current_version_id: string | null;
  current_release_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface RecordRow {
  id: string;
  revision: number;
  values: Record<string, unknown>;
  provenance?: Record<string, { source: string }>;
  created_at: string;
  updated_at: string;
}

export interface CreationFailure {
  reason: string;
  message: string;
  next_step: "retry" | "revise";
  failed_checks?: string[];
  attempts?: number;
}

export interface CreationResult {
  app_id: string;
  name: string | null;
  actions: string[];
  has_ui: boolean;
  checks_passed: number;
  preview_images: { name: string; url: string }[];
  attempts: number;
  /** For a change: exactly what the person will see differently, in one sentence. */
  summary?: string | null;
  changed_files?: string[];
  /** The fast lane: behaviour checks that run after a simple module is switched on. Absent
   *  when everything was checked before. */
  checks?: CreationChecks | null;
}

export interface CreationChecks {
  status: "pending" | "passed" | "failed" | "not_run";
  checks_passed?: number;
  failed_checks?: string[];
  reason?: string;
}

/** Where a module's latest fast-lane checks stand, from its own page. */
export interface AppChecks extends CreationChecks {
  creation_id: string;
  change_of: string | null;
  release_id: string | null;
}

export interface Creation {
  creation_id: string;
  conversation_id: string;
  brief_id: string;
  brief_revision: number;
  app_id: string | null;
  app_name: string | null;
  /** Set when this creation updates a module that already exists. */
  change_of?: string | null;
  release_id?: string | null;
  version_id?: string | null;
  state: "planning" | "building" | "checking" | "activating" | "active" | "failed" | "cancelled";
  stage: string;
  label: string;
  detail: string | null;
  progress: { attempt?: number; max_attempts?: number; checks_run?: number; checks_failed?: number };
  result: CreationResult | null;
  failure: CreationFailure | null;
  history: { stage: string; label: string; at: string }[];
  created_at: string;
  updated_at: string;
}

export const CREATION_DONE = new Set(["active", "failed", "cancelled"]);

/** One sentence the desktop assistant acted on, and what happened. */
export interface ActTurn {
  turn_id: string;
  text: string;
  kind: "run" | "query" | "open" | "build" | "change" | "answer";
  app_id: string | null;
  app_name?: string | null;
  action_id: string | null;
  run_id: string | null;
  conversation_id: string | null;
  /** Where the main window should go: a module (and tab) or a conversation. */
  open: { app_id?: string | null; tab_id?: string | null; conversation_id?: string | null } | null;
  reply: string;
  created_at: string;
}

export interface ActClient {
  /** Do what the sentence asks, at once; resolves when Alpha can say what happened. */
  act(text: string, appId?: string | null): Promise<ActTurn>;
  recentActs(): Promise<ActTurn[]>;
}

/** Creating results and using them (F08 routes). */
export interface WorkflowsClient {
  listApps(): Promise<AppSummary[]>;
  appDetail(appId: string): Promise<AppDetail>;
  startCreation(conversationId: string): Promise<Creation>;
  creation(creationId: string): Promise<Creation>;
  conversationCreations(conversationId: string): Promise<Creation[]>;
  cancelCreation(creationId: string): Promise<Creation>;
  /** The most recent creations, newest first (in progress and finished). */
  recentCreations(): Promise<Creation[]>;
  /** The module's latest behaviour checks (fast lane), or null when none apply. */
  appChecks(appId: string): Promise<AppChecks | null>;
  /** Back to the previous version; records are kept. */
  revertApp(appId: string, expectedReleaseId?: string | null): Promise<{ release_id: string }>;
  /** Take the module out of use; nothing on disk is deleted. */
  removeApp(appId: string, expectedReleaseId?: string | null): Promise<void>;
  runAppAction(appId: string, actionId: string, input: Record<string, unknown>, origin?: "ui" | "user"): Promise<Run>;
  operationOutcome(runId: string): Promise<OperationOutcome>;
  cancelRun(runId: string): Promise<Run>;
  queryRecords(appId: string, collection: string, limit?: number): Promise<RecordRow[]>;
  /** A page of a collection with a cursor, for the Data section. */
  queryRecordsPage?(appId: string, body: Record<string, unknown>): Promise<RecordPageResult>;
  /** A person's own change to a module's data: create, correct or delete one record. */
  mutateRecord?(appId: string, mutation: Record<string, unknown>): Promise<RecordRow | null>;
  listRuns(): Promise<Run[]>;
  /** An authenticated image from Core (check screenshots), as an object URL. */
  imageUrl(path: string): Promise<string>;
}

export function isWorkflowsClient(client: unknown): client is WorkflowsClient {
  return typeof (client as Partial<WorkflowsClient>)?.startCreation === "function";
}

export interface OperationOutcome {
  operation_id: string;
  state: string;
  output: Record<string, unknown> | null;
  error: { code: string; message: string } | null;
}

/** Installed-App commands used by the shell's bridge host (F05/F06 routes). */
export interface AppsClient {
  /** The signed-in browser, per module: what it may read through and what it opened. */
  browserAccess(appId: string): Promise<BrowserAccess[]>;
  setBrowserAccess(appId: string, sites: string[]): Promise<BrowserAccess[]>;
  browserVisits(appId: string): Promise<BrowserVisit[]>;
  appDetail(appId: string): Promise<AppDetail>;
  installFixtureApp(name: string): Promise<{ app_id: string }>;
  runAppAction(appId: string, actionId: string, input: Record<string, unknown>, origin?: "ui" | "user"): Promise<Run>;
  queryView(appId: string, viewId: string, body: Record<string, unknown>): Promise<unknown>;
  operationOutcome(runId: string): Promise<OperationOutcome>;
  listSchedules?(appId: string): Promise<ScheduleStatus[]>;
  setSchedule?(appId: string, scheduleId: string, enabled: boolean): Promise<ScheduleStatus[]>;
  runSchedule?(appId: string, scheduleId: string): Promise<ScheduleStatus[]>;
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

/** Every request Core serves returns promptly (long work runs in the background and is
 *  polled), so a request still open after this long means Core is stalled. It fails, and the
 *  caller's polling reports "reconnecting" and keeps asking; without a limit one stalled request
 *  froze a progress card indefinitely. */
export const REQUEST_TIMEOUT_MS = 20_000;

export class HttpCoreClient implements CoreClient, AppsClient, WorkflowsClient, ActClient {
  constructor(
    private readonly session: CoreSession,
    private readonly fetchImpl: typeof fetch = (...args) => fetch(...args),
    private readonly timeoutMs = REQUEST_TIMEOUT_MS,
  ) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.fetchImpl(`${this.session.baseUrl}${path}`, {
      ...init,
      signal: init.signal ?? AbortSignal.timeout(this.timeoutMs),
      headers: {
        Authorization: `Bearer ${this.session.token}`,
        "Content-Type": "application/json",
        ...(init.headers ?? {}),
      },
    }).catch((error: unknown) => {
      // Matched by name: the abort reason's DOMException may come from another realm.
      if ((error as { name?: unknown } | null)?.name === "TimeoutError") {
        throw new CoreError("Alpha's runtime did not answer in time.", 0, "timeout");
      }
      throw error;
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

  runAppAction(appId: string, actionId: string, input: Record<string, unknown>, origin: "ui" | "user" = "ui"): Promise<Run> {
    return this.request<Run>(`/api/apps/${encodeURIComponent(appId)}/actions/${encodeURIComponent(actionId)}/runs`, {
      method: "POST",
      body: JSON.stringify({ input, origin }),
    });
  }

  async listApps(): Promise<AppSummary[]> {
    const page = await this.request<{ apps: AppSummary[] }>("/api/apps");
    return page.apps;
  }

  startCreation(conversationId: string): Promise<Creation> {
    return this.request<Creation>(`/api/conversations/${encodeURIComponent(conversationId)}/creations`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  }

  creation(creationId: string): Promise<Creation> {
    return this.request<Creation>(`/api/creations/${encodeURIComponent(creationId)}`);
  }

  async conversationCreations(conversationId: string): Promise<Creation[]> {
    const page = await this.request<{ creations: Creation[] }>(
      `/api/conversations/${encodeURIComponent(conversationId)}/creations`,
    );
    return page.creations;
  }

  cancelCreation(creationId: string): Promise<Creation> {
    return this.request<Creation>(`/api/creations/${encodeURIComponent(creationId)}/cancel`, { method: "POST" });
  }

  async queryRecordsPage(appId: string, body: Record<string, unknown>): Promise<RecordPageResult> {
    return this.request<RecordPageResult>(`/api/apps/${encodeURIComponent(appId)}/records/query`, { method: "POST", body: JSON.stringify(body) });
  }

  async mutateRecord(appId: string, mutation: Record<string, unknown>): Promise<RecordRow | null> {
    const reply = await this.request<{ record: RecordRow | null }>(`/api/apps/${encodeURIComponent(appId)}/records/mutate`, {
      method: "POST",
      body: JSON.stringify({ mutation }),
    });
    return reply.record;
  }

  async queryRecords(appId: string, collection: string, limit = 50): Promise<RecordRow[]> {
    const page = await this.request<{ records: RecordRow[] }>(`/api/apps/${encodeURIComponent(appId)}/records/query`, {
      method: "POST",
      body: JSON.stringify({ collection, limit, order_by: [{ field: "created_at", direction: "desc" }] }),
    });
    return page.records;
  }

  async imageUrl(path: string): Promise<string> {
    if (!path.startsWith("/api/")) throw new CoreError("not a Core path", 400);
    const response = await this.fetchImpl(`${this.session.baseUrl}${path}`, {
      headers: { Authorization: `Bearer ${this.session.token}` },
    });
    if (!response.ok) throw new CoreError("image unavailable", response.status);
    return URL.createObjectURL(await response.blob());
  }

  queryView(appId: string, viewId: string, body: Record<string, unknown>): Promise<unknown> {
    return this.request(`/api/apps/${encodeURIComponent(appId)}/views/${encodeURIComponent(viewId)}/query`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async listSchedules(appId: string): Promise<ScheduleStatus[]> {
    const page = await this.request<{ schedules: ScheduleStatus[] }>(`/api/apps/${encodeURIComponent(appId)}/schedules`);
    return page.schedules;
  }

  async setSchedule(appId: string, scheduleId: string, enabled: boolean): Promise<ScheduleStatus[]> {
    const page = await this.request<{ schedules: ScheduleStatus[] }>(
      `/api/apps/${encodeURIComponent(appId)}/schedules/${encodeURIComponent(scheduleId)}`,
      { method: "POST", body: JSON.stringify({ enabled }) },
    );
    return page.schedules;
  }

  async runSchedule(appId: string, scheduleId: string): Promise<ScheduleStatus[]> {
    const page = await this.request<{ schedules: ScheduleStatus[] }>(
      `/api/apps/${encodeURIComponent(appId)}/schedules/${encodeURIComponent(scheduleId)}/run`,
      { method: "POST" },
    );
    return page.schedules;
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

  startConversation(text: string, changeOf?: string | null): Promise<Conversation> {
    const body: Record<string, unknown> = { text };
    if (changeOf) body.change_of = changeOf;
    return this.request<Conversation>("/api/conversations", { method: "POST", body: JSON.stringify(body) });
  }

  conversation(id: string): Promise<Conversation> {
    return this.request<Conversation>(`/api/conversations/${encodeURIComponent(id)}`);
  }

  async appConversations(appId: string): Promise<Conversation[]> {
    const page = await this.request<{ conversations: Conversation[] }>(`/api/apps/${encodeURIComponent(appId)}/conversations`);
    return page.conversations;
  }

  browserSites(): Promise<{ available: boolean; sites: BrowserSite[] }> {
    return this.request<{ available: boolean; sites: BrowserSite[] }>("/api/browser/sites");
  }

  connectBrowserSite(site: string): Promise<{ site: string; state: string }> {
    return this.request<{ site: string; state: string }>("/api/browser/sites", { method: "POST", body: JSON.stringify({ site }) });
  }

  async removeBrowserSite(site: string): Promise<void> {
    await this.request<{ removed: string }>(`/api/browser/sites/${encodeURIComponent(site)}`, { method: "DELETE" });
  }

  async browserAccess(appId: string): Promise<BrowserAccess[]> {
    const page = await this.request<{ sites: BrowserAccess[] }>(`/api/apps/${encodeURIComponent(appId)}/browser-access`);
    return page.sites;
  }

  async setBrowserAccess(appId: string, sites: string[]): Promise<BrowserAccess[]> {
    const page = await this.request<{ sites: BrowserAccess[] }>(`/api/apps/${encodeURIComponent(appId)}/browser-access`, { method: "PUT", body: JSON.stringify({ sites }) });
    return page.sites;
  }

  async browserVisits(appId: string): Promise<BrowserVisit[]> {
    const page = await this.request<{ visits: BrowserVisit[] }>(`/api/apps/${encodeURIComponent(appId)}/browser-visits`);
    return page.visits;
  }

  async getSettings(): Promise<SettingField[]> {
    const page = await this.request<{ settings: SettingField[] }>("/api/settings");
    return page.settings;
  }

  async updateSettings(values: Record<string, unknown>): Promise<SettingField[]> {
    const page = await this.request<{ settings: SettingField[] }>("/api/settings", { method: "PUT", body: JSON.stringify({ values }) });
    return page.settings;
  }

  async listConversations(): Promise<Conversation[]> {
    const page = await this.request<{ conversations: Conversation[] }>("/api/conversations?limit=20");
    return page.conversations;
  }

  cancelConversation(id: string): Promise<Conversation> {
    return this.request<Conversation>(`/api/conversations/${encodeURIComponent(id)}/cancel`, { method: "POST" });
  }

  retryConversation(id: string): Promise<Conversation> {
    return this.request<Conversation>(`/api/conversations/${encodeURIComponent(id)}/retry`, { method: "POST" });
  }

  async recentCreations(): Promise<Creation[]> {
    const page = await this.request<{ creations: Creation[] }>("/api/creations");
    return page.creations;
  }

  act(text: string, appId?: string | null): Promise<ActTurn> {
    // A run may take a while; the avatar waits for the outcome rather than a promise.
    return this.request<ActTurn>("/api/act", { method: "POST", body: JSON.stringify({ text, app_id: appId ?? null }), signal: AbortSignal.timeout(300_000) });
  }

  async recentActs(): Promise<ActTurn[]> {
    const page = await this.request<{ turns: ActTurn[] }>("/api/act");
    return page.turns;
  }

  async appChecks(appId: string): Promise<AppChecks | null> {
    const page = await this.request<{ checks: AppChecks | null }>(`/api/apps/${encodeURIComponent(appId)}/checks`);
    return page.checks;
  }

  revertApp(appId: string, expectedReleaseId?: string | null): Promise<{ release_id: string }> {
    return this.request<{ release_id: string }>(`/api/apps/${encodeURIComponent(appId)}/revert`, {
      method: "POST",
      body: JSON.stringify({ expected_release_id: expectedReleaseId ?? null }),
    });
  }

  async removeApp(appId: string, expectedReleaseId?: string | null): Promise<void> {
    await this.request(`/api/apps/${encodeURIComponent(appId)}/remove`, {
      method: "POST",
      body: JSON.stringify({ expected_release_id: expectedReleaseId ?? null }),
    });
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
