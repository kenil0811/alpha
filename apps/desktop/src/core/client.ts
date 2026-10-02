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

/** One thing attached to a message, as Core reads it (see AttachmentIn, services/core). `path`
 *  is a local file or folder Core reads directly (desktop); `content_b64` is its bytes when the
 *  browser sent them instead (web) — only ever set for a single file, never a folder. */
export interface AttachmentWire {
  kind: "file" | "image" | "folder" | "audio";
  name: string;
  size?: number | null;
  mime?: string | null;
  path?: string | null;
  content_b64?: string | null;
}

/** What was attached to a turn, as kept on its own record (name, kind, size — never bytes or
 *  the raw path). */
export interface AttachmentSummary {
  kind: "file" | "image" | "folder" | "audio";
  name: string;
  size?: number | null;
  mime?: string | null;
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

export type ConversationState = "thinking" | "researching" | "proposed" | "waiting_for_user" | "briefed" | "answered" | "failed";

/** After Alpha looked around: shaped options to choose from, and the evidence behind them. */
export interface Proposal {
  intro: string;
  options: { id: string; title: string; summary: string; why: string }[];
  default: string;
  evidence: { kind: string; title: string; url: string; note: string }[];
  /** What the research found that the person would care about, a line each. */
  findings?: string[];
  /** Only the decisions that change what gets built, answered along with the pick. */
  questions?: OpenQuestion[];
}

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
  proposal?: Proposal | null;
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

/** Settings -> Models: one provider's sign-in / key state, as Core reports it. */
export interface ModelProviderAccount {
  id: "claude" | "claude_api" | "chatgpt" | "chatgpt_api" | "openrouter" | "grok" | "groq";
  label: string;
  state: "connected" | "needs_sign_in" | "needs_key" | "cli_missing" | "key_saved" | "not_configured";
  cli_present: boolean | null;
  signed_in: boolean | null;
  key_last4: string | null;
  /** The Settings -> Models status dot: grey (not connected), green (connected), red (error) -
   *  tooltip is the exact state to show on hover. Cached in Core for about a minute. */
  dot: { color: "green" | "grey" | "red"; tooltip: string };
  /** Set on a sign-in answer when the browser page shows a code to paste back (Claude). */
  needs_code?: boolean;
  /** Codex is being installed in the background (npm); poll until it clears. */
  installing?: boolean;
  /** The last background install failed. */
  install_failed?: boolean;
  /** The provider in effect: the `models.provider` setting, or claude when it is unset. */
  default?: boolean;
}

/** One model a provider offers, for the model picker next to it. */
export interface ProviderModel {
  id: string;
  label: string;
}

/** Model provider accounts: keys live in the macOS Keychain, never round-tripped to the UI. */
export interface ModelAccountsClient {
  listModelAccounts(): Promise<ModelProviderAccount[]>;
  saveModelKey(provider: string, key: string): Promise<ModelProviderAccount>;
  removeModelKey(provider: string): Promise<ModelProviderAccount>;
  testModelAccount(provider: string): Promise<{ ok: boolean; message: string }>;
  /** Clear Alpha's own cached connection state and re-probe; for a key-based provider this also
   *  clears the saved key so the person is prompted again. Never touches a CLI sign-in itself. */
  reconnectModelAccount(provider: string): Promise<ModelProviderAccount>;
  /** Open the provider CLI's own browser sign-in (`claude auth login`, `codex login`); poll
   *  listModelAccounts to see it land. */
  signInModelAccount(provider: string): Promise<ModelProviderAccount>;
  /** Claude: the code its sign-in page showed, exchanged by Core for tokens (Keychain). */
  finishModelSignIn(provider: string, code: string): Promise<ModelProviderAccount>;
  /** Make the provider's CLI available without a terminal (ChatGPT: link or install Codex). */
  installModelCli(provider: string): Promise<ModelProviderAccount>;
  /** The models this provider offers, and the one chosen for it (null = provider's own default). */
  listProviderModels(provider: string): Promise<{ models: ProviderModel[]; selected: string | null }>;
  setProviderModel(provider: string, model: string): Promise<void>;
}

/** A Core older than the status dot sends rows without one; draw those grey rather than crash. */
function withDot(p: ModelProviderAccount): ModelProviderAccount {
  return p.dot ? p : { ...p, dot: { color: "grey", tooltip: p.state === "connected" || p.state === "key_saved" ? "Connected." : "Not connected" } };
}

export function isModelAccountsClient(client: unknown): client is ModelAccountsClient {
  return typeof (client as Partial<ModelAccountsClient>)?.listModelAccounts === "function";
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
  /** Other modules this one reads, as declared. */
  uses?: { module: string; views: string[]; purpose: string }[];
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
  fields: { name: string; kind: string; required?: boolean; description?: string; choices?: string[] | null; done_choices?: string[] | null; module?: string | null; collection?: string | null }[];
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
  next_step: "retry" | "revise" | "connect";
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
  /** "preliminary": checked only on the request's own examples, because Alpha's full checks
   *  were not ready in time; `full` says whether they are still coming. */
  status: "pending" | "passed" | "failed" | "not_run" | "preliminary";
  full?: "pending" | "unavailable";
  checks_passed?: number;
  failed_checks?: string[];
  reason?: string;
}

/** Checks that are still running after the module was switched on. */
export function checksOwed(checks: CreationChecks | null | undefined): boolean {
  return checks?.status === "pending" || (checks?.status === "preliminary" && checks.full === "pending");
}

/** Where a module's latest fast-lane checks stand, from its own page. */
/** A failed run of a module, diagnosed in plain words, and what Alpha did about it. */
export interface ModuleFailure {
  run_id: string;
  app_id: string;
  action_id: string;
  at: string;
  kind: "module_code" | "platform" | "outside" | "refusal" | "unknown";
  where: string | null;
  said: string;
  repair: { repair_id: string; state: "fixing" | "fixed" | "not_fixed"; summary: string } | null;
}

export interface ModuleRepair {
  repair_id: string;
  app_id: string;
  run_id: string;
  action_id: string | null;
  kind: string;
  state: "fixing" | "fixed" | "not_fixed";
  summary: string;
  created_at: string;
  updated_at: string;
}

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
  session_id?: string | null;
  text: string;
  kind: "run" | "query" | "skill" | "open" | "build" | "change" | "continue" | "answer";
  app_id: string | null;
  app_name?: string | null;
  action_id: string | null;
  run_id: string | null;
  conversation_id: string | null;
  /** Where the main window should go: a module (and tab), or a session and its conversation. */
  open: { app_id?: string | null; tab_id?: string | null; conversation_id?: string | null; session_id?: string | null } | null;
  reply: string;
  created_at: string;
  outcome?: string | null;
  attachments?: AttachmentSummary[] | null;
  model_error?: ModelErrorInfo | null;
}

/** A model call itself failed: which guided fix applies (a CLI sign-in, a key, or nothing
 *  actionable beyond trying again) and which Settings -> Models provider it was about. */
export interface ModelErrorInfo {
  kind: "sign_in" | "key" | "generic";
  provider: string;
}

/** A goal in the person's life that groups modules and the sessions about them. Optional. */
export interface Project {
  project_id: string;
  name: string;
  goal: string | null;
  /** Alpha's own notes on the project, kept from its sessions; the person may edit or clear them. */
  summary: string | null;
  modules: string[];
  /** A kebab-case lucide name Core picks (or the person does); null shows the folder. */
  icon?: string | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

/** A project's stored markdown artifact (its plan, its bug list); text is null until written. */
export interface ProjectFile {
  name: string;
  text: string | null;
  updated_at: string | null;
}

/** One turn of a session: what the person said, or what Alpha said and did. */
export interface SessionTurn {
  turn_id: string;
  sequence: number;
  role: "user" | "alpha";
  /** "work": Alpha did something (a card): started a conversation, ran actions, opened a module. */
  kind: "text" | "work";
  text: string;
  conversation_id?: string | null;
  open?: { app_id?: string | null; tab_id?: string | null; conversation_id?: string | null; session_id?: string | null } | null;
  /** One line of truth about what the turn led to, current when read. */
  outcome?: string | null;
  detail?: Record<string, unknown> | null;
  attachments?: AttachmentSummary[] | null;
  created_at: string;
}

/** A durable chat with Alpha: in a project, or global. */
export interface Session {
  session_id: string;
  project_id: string | null;
  title: string | null;
  focus_app_id: string | null;
  origin: "shell" | "avatar";
  state: "idle" | "thinking";
  /** Alpha's notes on the turns folded away; the rest are in `turns`. */
  summary: string | null;
  turns: SessionTurn[];
  turn_count: number;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface SessionSummary {
  session_id: string;
  project_id: string | null;
  title: string | null;
  focus_app_id: string | null;
  origin: "shell" | "avatar";
  state: "idle" | "thinking";
  turn_count: number;
  last_text: string | null;
  created_at: string;
  updated_at: string;
}

/** The + menu's Advanced choices for one message (see assistant/advanced.ts): unset falls back
 *  to the session's own remembered choice, then Settings -> Access. */
export interface AdvancedOptions {
  accessMode?: "ask" | "approve_for_me" | "full";
  model?: { provider: string; model?: string };
}

export interface SessionsClient {
  listProjects(): Promise<Project[]>;
  createProject(name: string, goal?: string | null): Promise<Project>;
  updateProject(projectId: string, patch: { name?: string; goal?: string; summary?: string; icon?: string; archived?: boolean }): Promise<Project>;
  /** Put a module in a project, or (null) take it out of every project. */
  fileModule(appId: string, projectId: string | null): Promise<void>;
  project(projectId: string): Promise<{ project: Project; sessions: SessionSummary[]; facts?: { facts: ProfileFact[]; suggestions: ProfileFact[] } }>;
  projectFile(projectId: string, name: "plan.md" | "bugs.md"): Promise<ProjectFile>;
  listSessions(scope: "all" | "global" | "project" | "module", projectId?: string | null, focusAppId?: string | null): Promise<SessionSummary[]>;
  createSession(draft: { project_id?: string | null; focus_app_id?: string | null; title?: string | null }): Promise<Session>;
  getSession(sessionId: string): Promise<Session>;
  /** Say something; Alpha works it through in the background (poll the session while `thinking`).
   *  `options` are the + menu's Advanced choices for this one message; omitted falls back to
   *  Settings -> Access. */
  sendSession(sessionId: string, text: string, appId?: string | null, attachments?: AttachmentWire[], options?: AdvancedOptions): Promise<Session>;
  updateSession(sessionId: string, patch: { title?: string; archived?: boolean }): Promise<Session>;
}

export function isSessionsClient(client: unknown): client is SessionsClient {
  return typeof (client as Partial<SessionsClient>)?.sendSession === "function";
}

/** One fact Alpha knows about the person, with where it came from. */
export interface ProfileFact {
  fact_id: string;
  field: string;
  value: unknown;
  provenance: "person" | "module" | "assistant" | "inferred";
  source: string;
  why?: string | null;
  confidence: number;
  state: "accepted" | "suggested" | "rejected" | "retracted";
  supersedes?: string | null;
  recorded_at: string;
}

/** One declared use of another module, with the person's switch. */
export interface ModuleConnection {
  module: string;
  name: string;
  purpose: string;
  views: { id: string; collection: string | null; kind: string | null }[];
  enabled: boolean;
  installed: boolean;
}

export interface ConnectionsClient {
  connections(appId: string): Promise<ModuleConnection[]>;
  setConnection(appId: string, module: string, enabled: boolean): Promise<ModuleConnection[]>;
  /** Rows of a connected module's collection to choose a relation from. */
  relatedPick(appId: string, module: string, collection: string, q?: string): Promise<{ id: string; title: string }[]>;
  relatedGet(appId: string, module: string, collection: string, recordId: string): Promise<{ id: string; title: string; values: Record<string, unknown> }>;
}

export function isConnectionsClient(client: unknown): client is ConnectionsClient {
  return typeof (client as Partial<ConnectionsClient>)?.connections === "function";
}

/** The first conversation: five questions, then a proposed first shape. */
export interface OnboardingStatus {
  done: boolean;
  questions: { id: string; label: string; hint: string }[];
  proposal: { intro: string; options: { title: string; request: string; why: string }[]; skipped?: boolean } | null;
}

/** Something Alpha noticed in its weekly look, with a next step to send as a request. */
export interface Nudge {
  nudge_id: string;
  text: string;
  next_step: string;
  module?: string | null;
  created_at: string;
}

export interface ProfileClient {
  nudges(): Promise<{ nudges: Nudge[]; last_run: string | null }>;
  reviewNow(): Promise<Nudge[]>;
  dismissNudge(nudgeId: string): Promise<void>;
  onboarding(): Promise<OnboardingStatus>;
  answerOnboarding(answers: Record<string, string>): Promise<OnboardingStatus>;
  skipOnboarding(): Promise<OnboardingStatus>;
  profile(): Promise<{ facts: ProfileFact[]; suggestions: ProfileFact[] }>;
  addFact(field: string, value: unknown): Promise<ProfileFact>;
  acceptFact(factId: string): Promise<ProfileFact>;
  rejectFact(factId: string): Promise<void>;
  forgetFact(factId: string): Promise<void>;
}

export interface SkillInput {
  name: string;
  description: string;
  required: boolean;
}

export interface SkillDraft {
  title: string;
  description: string;
  kind: "procedure" | "code";
  instructions: string;
  module: string | null;
  action: string | null;
  inputs: SkillInput[];
  produces: string;
  sources: string[];
}

export interface SkillSpec extends SkillDraft {
  id: string;
  created_by: "person" | "assistant";
  state: "active" | "retired";
  created_at: string;
  updated_at: string;
}

export interface SkillRun {
  run_id: string;
  skill_id: string;
  inputs: Record<string, unknown>;
  state: "running" | "done" | "failed";
  summary: string;
  items: Record<string, unknown>[];
  evidence: Record<string, unknown>[];
  started_at: string;
  finished_at: string | null;
}

export interface SchedulesClient {
  listSchedules?(appId: string): Promise<ScheduleStatus[]>;
  setSchedule?(appId: string, scheduleId: string, enabled: boolean): Promise<ScheduleStatus[]>;
}

export interface SkillsClient {
  /** The abilities Alpha keeps outside any module: listed, made, changed, run, retired. */
  listSkills(): Promise<SkillSpec[]>;
  createSkill(draft: SkillDraft): Promise<SkillSpec>;
  getSkill(skillId: string): Promise<{ skill: SkillSpec; runs: SkillRun[] }>;
  updateSkill(skillId: string, draft: SkillDraft): Promise<SkillSpec>;
  retireSkill(skillId: string): Promise<void>;
  runSkill(skillId: string, inputs: Record<string, unknown>): Promise<SkillRun>;
}

export function isSkillsClient(client: unknown): client is SkillsClient {
  return typeof (client as Partial<SkillsClient>)?.listSkills === "function";
}

export function isProfileClient(client: unknown): client is ProfileClient {
  return typeof (client as Partial<ProfileClient>)?.profile === "function";
}

export interface ActClient {
  /** Do what the sentence asks, at once; resolves when Alpha can say what happened. */
  act(text: string, appId?: string | null, attachments?: AttachmentWire[], options?: AdvancedOptions): Promise<ActTurn>;
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
  /** Recent failures of the module with their cause in words, and the fixes Alpha made. */
  appRepairs(appId: string): Promise<{ failures: ModuleFailure[]; repairs: ModuleRepair[] }>;
  /** Back to the previous version; records are kept. */
  revertApp(appId: string, expectedReleaseId?: string | null): Promise<{ release_id: string }>;
  /** Remove the module for good, with its records, history and what was said about it. */
  removeApp(appId: string, expectedReleaseId?: string | null): Promise<void>;
  /** Modules taken out of use before removal deleted things: still on this Mac. */
  removedModules(): Promise<{ app_id: string; name: string }[]>;
  /** Delete those for good. */
  deleteRemovedModules(): Promise<number>;
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
  /** The module's current source, packaged as a portable `.alphamodule` file (a zip): later,
   *  an attachment anyone else building on Alpha can add as a new module. */
  exportModule(appId: string): Promise<Blob>;
  /** Install a `.alphamodule` file (from disk, or dropped/attached) as a new module. */
  importModuleFile(file: File | Blob | { path: string }): Promise<{ app_id: string; name: string }>;
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

export class HttpCoreClient implements CoreClient, AppsClient, WorkflowsClient, ActClient, ProfileClient, ConnectionsClient, SessionsClient, ModelAccountsClient {
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

  async exportModule(appId: string): Promise<Blob> {
    const response = await this.fetchImpl(`${this.session.baseUrl}/api/apps/${encodeURIComponent(appId)}/export`, {
      headers: { Authorization: `Bearer ${this.session.token}` },
    });
    if (!response.ok) throw new CoreError("couldn't export this project", response.status);
    return response.blob();
  }

  async importModuleFile(file: File | Blob | { path: string }): Promise<{ app_id: string; name: string }> {
    if ("path" in file) {
      return this.request<{ app_id: string; name: string }>("/api/modules/import", { method: "POST", body: JSON.stringify({ path: file.path }) });
    }
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
    const data_base64 = btoa(binary);
    return this.request<{ app_id: string; name: string }>("/api/modules/import", {
      method: "POST",
      body: JSON.stringify({ data_base64 }),
    });
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

  async listModelAccounts(): Promise<ModelProviderAccount[]> {
    const page = await this.request<{ providers: ModelProviderAccount[] }>("/api/model-accounts");
    return page.providers.map(withDot);
  }

  async saveModelKey(provider: string, key: string): Promise<ModelProviderAccount> {
    const page = await this.request<{ provider: ModelProviderAccount }>(`/api/model-accounts/${encodeURIComponent(provider)}/key`, {
      method: "PUT",
      body: JSON.stringify({ key }),
    });
    return withDot(page.provider);
  }

  async removeModelKey(provider: string): Promise<ModelProviderAccount> {
    const page = await this.request<{ provider: ModelProviderAccount }>(`/api/model-accounts/${encodeURIComponent(provider)}/key`, { method: "DELETE" });
    return withDot(page.provider);
  }

  testModelAccount(provider: string): Promise<{ ok: boolean; message: string }> {
    return this.request(`/api/model-accounts/${encodeURIComponent(provider)}/test`, { method: "POST" });
  }

  async reconnectModelAccount(provider: string): Promise<ModelProviderAccount> {
    const page = await this.request<{ provider: ModelProviderAccount }>(`/api/model-accounts/${encodeURIComponent(provider)}/reconnect`, { method: "POST" });
    return withDot(page.provider);
  }

  async signInModelAccount(provider: string): Promise<ModelProviderAccount> {
    const page = await this.request<{ provider: ModelProviderAccount }>(`/api/model-accounts/${encodeURIComponent(provider)}/sign-in`, { method: "POST" });
    return withDot(page.provider);
  }

  async installModelCli(provider: string): Promise<ModelProviderAccount> {
    const page = await this.request<{ provider: ModelProviderAccount }>(`/api/model-accounts/${encodeURIComponent(provider)}/install`, { method: "POST" });
    return withDot(page.provider);
  }

  async finishModelSignIn(provider: string, code: string): Promise<ModelProviderAccount> {
    const page = await this.request<{ provider: ModelProviderAccount }>(`/api/model-accounts/${encodeURIComponent(provider)}/sign-in/finish`, {
      method: "POST",
      body: JSON.stringify({ code }),
    });
    return withDot(page.provider);
  }

  listProviderModels(provider: string): Promise<{ models: ProviderModel[]; selected: string | null }> {
    return this.request(`/api/model-accounts/${encodeURIComponent(provider)}/models`);
  }

  async setProviderModel(provider: string, model: string): Promise<void> {
    await this.request(`/api/model-accounts/${encodeURIComponent(provider)}/model`, { method: "PUT", body: JSON.stringify({ model }) });
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

  async connections(appId: string): Promise<ModuleConnection[]> {
    const page = await this.request<{ connections: ModuleConnection[] }>(`/api/apps/${encodeURIComponent(appId)}/connections`);
    return page.connections;
  }

  async setConnection(appId: string, module: string, enabled: boolean): Promise<ModuleConnection[]> {
    const page = await this.request<{ connections: ModuleConnection[] }>(`/api/apps/${encodeURIComponent(appId)}/connections/${encodeURIComponent(module)}`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    });
    return page.connections;
  }

  async relatedPick(appId: string, module: string, collection: string, q = ""): Promise<{ id: string; title: string }[]> {
    const page = await this.request<{ rows: { id: string; title: string }[] }>(`/api/apps/${encodeURIComponent(appId)}/related/${encodeURIComponent(module)}/${encodeURIComponent(collection)}?q=${encodeURIComponent(q)}`);
    return page.rows;
  }

  relatedGet(appId: string, module: string, collection: string, recordId: string): Promise<{ id: string; title: string; values: Record<string, unknown> }> {
    return this.request(`/api/apps/${encodeURIComponent(appId)}/related/${encodeURIComponent(module)}/${encodeURIComponent(collection)}/${encodeURIComponent(recordId)}`);
  }

  nudges(): Promise<{ nudges: Nudge[]; last_run: string | null }> {
    return this.request("/api/nudges");
  }

  async reviewNow(): Promise<Nudge[]> {
    const page = await this.request<{ nudges: Nudge[] }>("/api/nudges/review", { method: "POST", signal: AbortSignal.timeout(120_000) });
    return page.nudges;
  }

  async dismissNudge(nudgeId: string): Promise<void> {
    await this.request(`/api/nudges/${encodeURIComponent(nudgeId)}/dismiss`, { method: "POST" });
  }

  onboarding(): Promise<OnboardingStatus> {
    return this.request("/api/onboarding");
  }

  answerOnboarding(answers: Record<string, string>): Promise<OnboardingStatus> {
    return this.request("/api/onboarding", { method: "POST", body: JSON.stringify({ answers }) });
  }

  skipOnboarding(): Promise<OnboardingStatus> {
    return this.request("/api/onboarding/skip", { method: "POST" });
  }

  profile(): Promise<{ facts: ProfileFact[]; suggestions: ProfileFact[] }> {
    return this.request("/api/profile");
  }

  async listSkills(): Promise<SkillSpec[]> {
    const page = await this.request<{ skills: SkillSpec[] }>("/api/skills");
    return page.skills;
  }

  createSkill(draft: SkillDraft): Promise<SkillSpec> {
    return this.request("/api/skills", { method: "POST", body: JSON.stringify(draft) });
  }

  getSkill(skillId: string): Promise<{ skill: SkillSpec; runs: SkillRun[] }> {
    return this.request(`/api/skills/${encodeURIComponent(skillId)}`);
  }

  updateSkill(skillId: string, draft: SkillDraft): Promise<SkillSpec> {
    return this.request(`/api/skills/${encodeURIComponent(skillId)}`, { method: "PUT", body: JSON.stringify(draft) });
  }

  async retireSkill(skillId: string): Promise<void> {
    await this.request(`/api/skills/${encodeURIComponent(skillId)}`, { method: "DELETE" });
  }

  runSkill(skillId: string, inputs: Record<string, unknown>): Promise<SkillRun> {
    // A run reads the web in steps; it is bounded in Core (150 s) so the wait here is longer.
    return this.request(`/api/skills/${encodeURIComponent(skillId)}/run`, { method: "POST", body: JSON.stringify({ inputs }), signal: AbortSignal.timeout(200_000) });
  }

  addFact(field: string, value: unknown): Promise<ProfileFact> {
    return this.request<ProfileFact>("/api/profile/facts", { method: "POST", body: JSON.stringify({ field, value }) });
  }

  acceptFact(factId: string): Promise<ProfileFact> {
    return this.request<ProfileFact>(`/api/profile/facts/${encodeURIComponent(factId)}/accept`, { method: "POST" });
  }

  async rejectFact(factId: string): Promise<void> {
    await this.request(`/api/profile/facts/${encodeURIComponent(factId)}/reject`, { method: "POST" });
  }

  async forgetFact(factId: string): Promise<void> {
    await this.request(`/api/profile/facts/${encodeURIComponent(factId)}/forget`, { method: "POST" });
  }

  act(text: string, appId?: string | null, attachments?: AttachmentWire[], options?: AdvancedOptions): Promise<ActTurn> {
    // A run may take a while; the avatar waits for the outcome rather than a promise.
    return this.request<ActTurn>("/api/act", {
      method: "POST",
      body: JSON.stringify({
        text,
        app_id: appId ?? null,
        attachments: attachments ?? [],
        access_mode: options?.accessMode ?? null,
        model: options?.model ?? null,
      }),
      signal: AbortSignal.timeout(300_000),
    });
  }

  async recentActs(): Promise<ActTurn[]> {
    const page = await this.request<{ turns: ActTurn[] }>("/api/act");
    return page.turns;
  }

  async removedModules(): Promise<{ app_id: string; name: string }[]> {
    const page = await this.request<{ modules: { app_id: string; name: string }[] }>("/api/removed-modules");
    return page.modules;
  }

  async deleteRemovedModules(): Promise<number> {
    const page = await this.request<{ deleted: unknown[] }>("/api/removed-modules/delete", { method: "POST", signal: AbortSignal.timeout(120_000) });
    return page.deleted.length;
  }

  appRepairs(appId: string): Promise<{ failures: ModuleFailure[]; repairs: ModuleRepair[] }> {
    return this.request(`/api/apps/${encodeURIComponent(appId)}/repairs`);
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

  async listProjects(): Promise<Project[]> {
    const page = await this.request<{ projects: Project[] }>("/api/projects");
    return page.projects;
  }

  createProject(name: string, goal?: string | null): Promise<Project> {
    return this.request<Project>("/api/projects", { method: "POST", body: JSON.stringify({ name, goal: goal ?? null }) });
  }

  updateProject(projectId: string, patch: { name?: string; goal?: string; summary?: string; icon?: string; archived?: boolean }): Promise<Project> {
    return this.request<Project>(`/api/projects/${encodeURIComponent(projectId)}`, { method: "POST", body: JSON.stringify(patch) });
  }

  async fileModule(appId: string, projectId: string | null): Promise<void> {
    await this.request(`/api/apps/${encodeURIComponent(appId)}/project`, { method: "POST", body: JSON.stringify({ project_id: projectId }) });
  }

  project(projectId: string): Promise<{ project: Project; sessions: SessionSummary[]; facts?: { facts: ProfileFact[]; suggestions: ProfileFact[] } }> {
    return this.request(`/api/projects/${encodeURIComponent(projectId)}`);
  }

  projectFile(projectId: string, name: "plan.md" | "bugs.md"): Promise<ProjectFile> {
    return this.request<ProjectFile>(`/api/projects/${encodeURIComponent(projectId)}/files/${encodeURIComponent(name)}`);
  }

  async listSessions(scope: "all" | "global" | "project" | "module", projectId?: string | null, focusAppId?: string | null): Promise<SessionSummary[]> {
    const query = new URLSearchParams({ scope });
    if (projectId) query.set("project_id", projectId);
    if (focusAppId) query.set("focus_app_id", focusAppId);
    const page = await this.request<{ sessions: SessionSummary[] }>(`/api/sessions?${query.toString()}`);
    return page.sessions;
  }

  createSession(draft: { project_id?: string | null; focus_app_id?: string | null; title?: string | null }): Promise<Session> {
    return this.request<Session>("/api/sessions", { method: "POST", body: JSON.stringify(draft) });
  }

  getSession(sessionId: string): Promise<Session> {
    return this.request<Session>(`/api/sessions/${encodeURIComponent(sessionId)}`);
  }

  sendSession(sessionId: string, text: string, appId?: string | null, attachments?: AttachmentWire[], options?: AdvancedOptions): Promise<Session> {
    return this.request<Session>(`/api/sessions/${encodeURIComponent(sessionId)}/messages`, {
      method: "POST",
      body: JSON.stringify({
        text,
        app_id: appId ?? null,
        attachments: attachments ?? [],
        access_mode: options?.accessMode ?? null,
        model: options?.model ?? null,
      }),
    });
  }

  updateSession(sessionId: string, patch: { title?: string; archived?: boolean }): Promise<Session> {
    return this.request<Session>(`/api/sessions/${encodeURIComponent(sessionId)}`, { method: "POST", body: JSON.stringify(patch) });
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
