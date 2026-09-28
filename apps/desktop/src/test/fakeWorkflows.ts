import type { Run } from "@alpha/contracts";
import { type AppChecks, type ModuleConnection, type ProfileFact,
  CREATION_DONE,
  type AppDetail,
  type AppsClient,
  type AppSummary,
  type Creation,
  type OperationOutcome,
  type RecordPageResult,
  type RecordRow,
  type WorkflowsClient,
} from "../core/client";
import { FakeCoreClient } from "./fakeClient";

/** FakeCoreClient plus the creation and workflow routes, with test controls for each. */
export class FakeWorkflowsClient extends FakeCoreClient implements WorkflowsClient, AppsClient {
  apps: AppSummary[] = [];
  details = new Map<string, AppDetail>();
  records = new Map<string, RecordRow[]>();
  creations = new Map<string, Creation>();
  /** What each started creation becomes on its next poll. */
  nextCreationState: ((creation: Creation) => Creation) | null = null;
  /** The outcome an App action run ends with. */
  actionOutcome: (actionId: string, input: Record<string, unknown>) => OperationOutcome["state"] = () => "succeeded";
  actionOutput: Record<string, unknown> = { id: "rec_1", revision: 1 };
  invocations: { appId: string; actionId: string; input: Record<string, unknown>; origin: string }[] = [];
  cancelled: string[] = [];
  imagesRequested: string[] = [];
  /** Test control: the next N creation status requests fail (a lost connection). */
  failNextPolls = 0;
  polls = 0;

  async listApps(): Promise<AppSummary[]> {
    return this.apps;
  }

  async appDetail(appId: string): Promise<AppDetail> {
    const detail = this.details.get(appId);
    if (!detail) throw new Error("app_not_found");
    return detail;
  }

  async installFixtureApp(): Promise<{ app_id: string }> {
    throw new Error("not in this fake");
  }

  /** Test control: what each declared view returns. */
  views = new Map<string, unknown>();
  viewQueries: { viewId: string; body: Record<string, unknown> }[] = [];

  async queryView(_appId: string, viewId: string, body: Record<string, unknown>): Promise<unknown> {
    this.viewQueries.push({ viewId, body });
    return this.views.get(viewId) ?? { records: [], next_cursor: null };
  }

  async startCreation(conversationId: string): Promise<Creation> {
    const now = new Date().toISOString();
    const creation: Creation = {
      creation_id: `cre_${this.creations.size + 1}`,
      conversation_id: conversationId,
      brief_id: "brief_1",
      brief_revision: 1,
      app_id: null,
      app_name: null,
      change_of: this.conversations.get(conversationId)?.change_of ?? null,
      state: "planning",
      stage: "planning",
      label: "Deciding how to check it",
      detail: null,
      progress: {},
      result: null,
      failure: null,
      history: [],
      created_at: now,
      updated_at: now,
    };
    this.creations.set(creation.creation_id, creation);
    return creation;
  }

  async creation(creationId: string): Promise<Creation> {
    this.polls += 1;
    if (this.failNextPolls > 0) {
      this.failNextPolls -= 1;
      throw new Error("Failed to fetch");
    }
    let creation = this.creations.get(creationId);
    if (!creation) throw new Error("creation_not_found");
    if (this.nextCreationState && !CREATION_DONE.has(creation.state)) {
      creation = this.nextCreationState(creation);
      this.creations.set(creationId, creation);
    }
    return creation;
  }

  async conversationCreations(conversationId: string): Promise<Creation[]> {
    return [...this.creations.values()].filter((c) => c.conversation_id === conversationId);
  }

  async recentCreations(): Promise<Creation[]> {
    return [...this.creations.values()].reverse();
  }

  connectionRows: ModuleConnection[] = [];
  related: Record<string, { id: string; title: string; values: Record<string, unknown> }[]> = {};

  async connections(): Promise<ModuleConnection[]> {
    return this.connectionRows;
  }

  async setConnection(_appId: string, module: string, enabled: boolean): Promise<ModuleConnection[]> {
    this.connectionRows = this.connectionRows.map((c) => (c.module === module ? { ...c, enabled } : c));
    return this.connectionRows;
  }

  async relatedPick(_appId: string, module: string, collection: string, q = ""): Promise<{ id: string; title: string }[]> {
    return (this.related[`${module}/${collection}`] ?? []).filter((r) => r.title.toLowerCase().includes(q.toLowerCase())).map((r) => ({ id: r.id, title: r.title }));
  }

  async relatedGet(_appId: string, module: string, collection: string, recordId: string) {
    const row = (this.related[`${module}/${collection}`] ?? []).find((r) => r.id === recordId);
    if (!row) throw new Error("not_found");
    return row;
  }

  facts: ProfileFact[] = [];
  suggestions: ProfileFact[] = [];
  factCalls: string[] = [];

  async profile(): Promise<{ facts: ProfileFact[]; suggestions: ProfileFact[] }> {
    return { facts: this.facts, suggestions: this.suggestions };
  }

  async addFact(field: string, value: unknown): Promise<ProfileFact> {
    this.factCalls.push(`add ${field}`);
    const fact: ProfileFact = { fact_id: `fact_${this.facts.length + 1}`, field, value, provenance: "person", source: "person", confidence: 1, state: "accepted", recorded_at: new Date().toISOString() };
    this.facts = [...this.facts.filter((f) => f.field !== field), fact];
    return fact;
  }

  async acceptFact(factId: string): Promise<ProfileFact> {
    this.factCalls.push(`accept ${factId}`);
    const fact = this.suggestions.find((s) => s.fact_id === factId)!;
    this.suggestions = this.suggestions.filter((s) => s.fact_id !== factId);
    this.facts = [...this.facts, { ...fact, state: "accepted" }];
    return fact;
  }

  async rejectFact(factId: string): Promise<void> {
    this.factCalls.push(`reject ${factId}`);
    this.suggestions = this.suggestions.filter((s) => s.fact_id !== factId);
  }

  async forgetFact(factId: string): Promise<void> {
    this.factCalls.push(`forget ${factId}`);
    this.facts = this.facts.filter((f) => f.fact_id !== factId);
  }

  checks: AppChecks | null = null;
  reverted: string[] = [];
  removed: string[] = [];

  async appChecks(): Promise<AppChecks | null> {
    return this.checks;
  }

  async revertApp(appId: string): Promise<{ release_id: string }> {
    this.reverted.push(appId);
    return { release_id: "rel_previous" };
  }

  async removeApp(appId: string): Promise<void> {
    this.removed.push(appId);
  }

  async cancelCreation(creationId: string): Promise<Creation> {
    const creation = { ...this.creations.get(creationId)!, state: "cancelled" as const, label: "Stopped" };
    this.creations.set(creationId, creation);
    return creation;
  }

  async runAppAction(appId: string, actionId: string, input: Record<string, unknown>, origin: "ui" | "user" = "ui"): Promise<Run> {
    this.invocations.push({ appId, actionId, input, origin });
    const run = await this.createRun({ text: actionId });
    this.start(run.run_id);
    const state = this.actionOutcome(actionId, input);
    if (state === "succeeded") this.succeed(run.run_id, this.actionOutput);
    else if (state === "failed") this.fail(run.run_id, "input_invalid");
    return this.run(run.run_id);
  }

  async operationOutcome(runId: string): Promise<OperationOutcome> {
    const run = await this.run(runId);
    if (run.state === "failed") {
      return { operation_id: runId, state: run.state, output: null, error: { code: "input_invalid", message: "The food is needed." } };
    }
    return { operation_id: runId, state: run.state, output: (run.output as Record<string, unknown>) ?? null, error: null };
  }

  async cancelRun(runId: string): Promise<Run> {
    this.cancelled.push(runId);
    return super.cancelRun(runId);
  }

  async queryRecords(appId: string, collection: string): Promise<RecordRow[]> {
    return this.records.get(`${appId}/${collection}`) ?? [];
  }

  mutations: Record<string, unknown>[] = [];

  async queryRecordsPage(appId: string, body: Record<string, unknown>): Promise<RecordPageResult> {
    return { records: this.records.get(`${appId}/${String(body.collection)}`) ?? [], next_cursor: null };
  }

  async mutateRecord(appId: string, mutation: Record<string, unknown>): Promise<RecordRow | null> {
    this.mutations.push(mutation);
    const key = `${appId}/${String(mutation.collection)}`;
    const rows = [...(this.records.get(key) ?? [])];
    if (mutation.op === "create") {
      const row: RecordRow = { id: `rec_${rows.length + 1}`, revision: 1, values: mutation.values as Record<string, unknown>, created_at: "", updated_at: "" };
      this.records.set(key, [row, ...rows]);
      return row;
    }
    const index = rows.findIndex((r) => r.id === mutation.id);
    if (index === -1) throw new Error("not_found");
    if (mutation.op === "delete") {
      rows.splice(index, 1);
      this.records.set(key, rows);
      return null;
    }
    const row = { ...rows[index], revision: rows[index].revision + 1, values: { ...rows[index].values, ...(mutation.changes as Record<string, unknown>) } };
    rows[index] = row;
    this.records.set(key, rows);
    return row;
  }

  async imageUrl(path: string): Promise<string> {
    this.imagesRequested.push(path);
    return `blob:${path}`;
  }
}

export function sampleSummary(overrides: Partial<AppSummary> = {}): AppSummary {
  return {
    app_id: "notes-list-1a2b3c",
    name: "Notes list",
    description: "Keep a notes list",
    origin: "created",
    state: "active",
    has_ui: false,
    actions: 2,
    current_version_id: "ver_1234567890abcdef",
    current_release_id: "rel_1",
    created_at: "2026-09-26T10:00:00Z",
    updated_at: "2026-09-26T10:00:00Z",
    ...overrides,
  };
}

export function sampleDetail(overrides: Partial<AppDetail> = {}): AppDetail {
  return {
    app_id: "notes-list-1a2b3c",
    name: "Notes list",
    description: "Keep a notes list",
    version_id: "ver_1234567890abcdef",
    release_id: "rel_1",
    package_sha256: "0".repeat(64),
    runtime_profile_id: "python-app-0.1",
    ui: null,
    actions: [
      {
        id: "add_note",
        title: "Add note",
        description: "Save one note",
        input_schema: {
          type: "object",
          properties: { title: { type: "string", description: "What to remember" }, pinned: { type: "boolean" } },
          required: ["title"],
        },
        output_schema: { type: "object" },
        invocable_from: ["manual", "ui"],
        effect_class: "local_write",
      },
    ],
    collections: [{ name: "notes", fields: [{ name: "title", kind: "text", required: true }, { name: "calories", kind: "number" }] }],
    record_counts: { notes: 0 },
    ...overrides,
  };
}
