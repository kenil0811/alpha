/**
 * An in-memory App behind a real bridge: a BridgeHost and BridgeClient joined by a
 * MessageChannel, with handlers that evaluate declared views and actions over plain arrays.
 * Used by kit tests, the reference sheet and generated-UI tests. It speaks exactly the protocol
 * the shell speaks, so a composition that works here uses nothing the real bridge lacks.
 */
import { BridgeClient, BridgeError, BridgeHost, type BridgeSession } from "@alpha/ui-bridge";
import type { FilterNode, SortKey } from "../data/query";
import type { RecordRow } from "../data/hooks";

export type Values = Record<string, unknown>;

export interface MemoryRecordsView {
  id: string;
  kind?: "records";
  collection: string;
  /** Fixed filter the UI cannot remove. */
  where?: FilterNode;
  default_order?: SortKey[];
  max_limit?: number;
}

export interface MemoryAggregateView {
  id: string;
  kind: "aggregate";
  collection: string;
  where?: FilterNode;
  group_by: Array<{ field: string; bucket?: "day" }>;
  metrics: Array<{ name: string; fn: "count" | "sum" | "avg" | "min" | "max"; field?: string }>;
}

export type MemoryView = MemoryRecordsView | MemoryAggregateView;

export interface MemoryStore {
  records: Record<string, RecordRow[]>;
  create(collection: string, values: Values): RecordRow;
  update(collection: string, id: string, expectedRevision: number, changes: Values): RecordRow;
  remove(collection: string, id: string, expectedRevision: number): void;
}

/** An action handler: return output, or throw an Error whose message the UI will show. */
export type MemoryAction = (input: Values, store: MemoryStore) => Values | Promise<Values>;

export interface MemoryAppOptions {
  collections?: Record<string, Values[]>;
  views: MemoryView[];
  actions?: Record<string, MemoryAction>;
  /** Simulated platform latency for actions, in milliseconds. */
  latencyMs?: number;
  /** Simulated latency for view queries (a very large value shows loading states). */
  queryLatencyMs?: number;
}

export interface MemoryApp {
  client: BridgeClient;
  host: BridgeHost;
  store: MemoryStore;
  /** Make the next invocation of `actionId` fail with `message` (a provider or save failure). */
  failNext(actionId: string, message: string): void;
  /** Make every view query fail with `message` until called with null (provider outage). */
  failQueries(message: string | null): void;
  revoke(reason: string): void;
}

let counter = 0;
const newId = () => `rec_${(++counter).toString(16).padStart(32, "0")}`;
const now = () => new Date().toISOString();

function compare(a: unknown, b: unknown): number {
  if (a === b) return 0;
  if (a === undefined || a === null) return -1;
  if (b === undefined || b === null) return 1;
  return (a as number | string) < (b as number | string) ? -1 : 1;
}

function field(row: RecordRow, name: string): unknown {
  if (name === "id") return row.id;
  if (name === "created_at") return row.created_at;
  if (name === "updated_at") return row.updated_at;
  return row.values[name];
}

export function matches(row: RecordRow, node: FilterNode | undefined): boolean {
  if (!node) return true;
  if ("all" in node) return node.all.every((n) => matches(row, n));
  if ("any" in node) return node.any.some((n) => matches(row, n));
  if ("not" in node) return !matches(row, node.not);
  const value = field(row, node.field);
  switch (node.op) {
    case "eq":
      return value === node.value;
    case "ne":
      return value !== node.value;
    case "lt":
      return value !== undefined && value !== null && compare(value, node.value) < 0;
    case "lte":
      return value !== undefined && value !== null && compare(value, node.value) <= 0;
    case "gt":
      return value !== undefined && value !== null && compare(value, node.value) > 0;
    case "gte":
      return value !== undefined && value !== null && compare(value, node.value) >= 0;
    case "in":
      return Array.isArray(node.value) && node.value.includes(value);
    case "contains":
      return typeof value === "string" && value.toLowerCase().includes(String(node.value).toLowerCase());
    case "starts_with":
      return typeof value === "string" && value.startsWith(String(node.value));
    case "is_null":
      return (value === undefined || value === null) === Boolean(node.value);
  }
}

function makeStore(initial: Record<string, Values[]>): MemoryStore {
  const records: Record<string, RecordRow[]> = {};
  for (const [collection, rows] of Object.entries(initial)) {
    records[collection] = rows.map((values) => ({ id: newId(), revision: 1, values: { ...values }, provenance: {}, created_at: now(), updated_at: now() }));
  }
  const find = (collection: string, id: string) => {
    const row = (records[collection] ?? []).find((r) => r.id === id);
    if (!row) throw new Error(`That item no longer exists.`);
    return row;
  };
  return {
    records,
    create(collection, values) {
      const row: RecordRow = { id: newId(), revision: 1, values: { ...values }, provenance: {}, created_at: now(), updated_at: now() };
      (records[collection] ??= []).push(row);
      return row;
    },
    update(collection, id, expectedRevision, changes) {
      const row = find(collection, id);
      if (row.revision !== expectedRevision) throw new Error(`This item changed since it was opened (revision ${row.revision}).`);
      for (const [key, value] of Object.entries(changes)) {
        if (value === null) delete row.values[key];
        else row.values[key] = value;
        delete row.provenance[key];
      }
      row.revision += 1;
      row.updated_at = now();
      return row;
    },
    remove(collection, id, expectedRevision) {
      const row = find(collection, id);
      if (row.revision !== expectedRevision) throw new Error(`This item changed since it was opened.`);
      records[collection] = records[collection].filter((r) => r.id !== id);
    },
  };
}

function aggregate(rows: RecordRow[], view: MemoryAggregateView) {
  const groups = new Map<string, { key: Values; rows: RecordRow[] }>();
  for (const row of rows) {
    const key: Values = {};
    for (const g of view.group_by) {
      const raw = field(row, g.field);
      key[g.bucket ? `${g.field}_${g.bucket}` : g.field] = g.bucket === "day" && typeof raw === "string" ? raw.slice(0, 10) : raw;
    }
    const id = JSON.stringify(key);
    if (!groups.has(id)) groups.set(id, { key, rows: [] });
    groups.get(id)!.rows.push(row);
  }
  const out = [...groups.values()].map(({ key, rows: members }) => {
    const values: Record<string, number | string | null> = {};
    for (const m of view.metrics) {
      const nums = members.map((r) => (m.field ? field(r, m.field) : null)).filter((v): v is number => typeof v === "number");
      if (m.fn === "count") values[m.name] = members.length;
      else if (m.fn === "sum") values[m.name] = nums.length ? nums.reduce((a, b) => a + b, 0) : null;
      else if (m.fn === "avg") values[m.name] = nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : null;
      else if (m.fn === "min") values[m.name] = nums.length ? Math.min(...nums) : null;
      else values[m.name] = nums.length ? Math.max(...nums) : null;
    }
    return { key, values };
  });
  out.sort((a, b) => compare(JSON.stringify(a.key), JSON.stringify(b.key)));
  return { groups: out, truncated: false };
}

export async function createMemoryApp(options: MemoryAppOptions): Promise<MemoryApp> {
  const store = makeStore(options.collections ?? {});
  const views = new Map(options.views.map((v) => [v.id, v]));
  const actions = options.actions ?? {};
  const failures = new Map<string, string>();
  const operations = new Map<string, { state: string; output?: Values; error?: { code: string; message: string } }>();
  const latency = options.latencyMs ?? 0;
  const queryLatency = options.queryLatencyMs ?? 0;
  let queryFailure: string | null = null;
  const session: BridgeSession = {
    session_id: `sess_memory_${++counter}`,
    owner: { kind: "app", app_id: "memory-app", release_id: "rel_memory" },
    grant: { actions: Object.keys(actions), read_views: [...views.keys()] },
    expires_at: new Date(Date.now() + 24 * 3600_000).toISOString(),
  };
  const host = new BridgeHost({
    session,
    handlers: {
      recordsQuery: async (_s, payload) => {
        if (queryLatency) await new Promise((resolve) => setTimeout(resolve, queryLatency));
        if (queryFailure !== null) throw new BridgeError("unsupported", queryFailure, "Try again in a moment.");
        const view = views.get(payload.view);
        if (!view) throw new BridgeError("not_found", `unknown view ${payload.view}`);
        const where = payload.where as FilterNode | undefined;
        const rows = (store.records[view.collection] ?? []).filter((r) => matches(r, view.where) && matches(r, where));
        if (view.kind === "aggregate") return aggregate(rows, view);
        const order = (payload.order_by as SortKey[] | undefined)?.length ? (payload.order_by as SortKey[]) : (view.default_order ?? []);
        const sorted = [...rows].sort((a, b) => {
          for (const key of order) {
            const c = compare(field(a, key.field), field(b, key.field));
            if (c !== 0) return key.direction === "desc" ? -c : c;
          }
          return compare(a.created_at + a.id, b.created_at + b.id);
        });
        const limit = Math.min(payload.limit ?? 50, view.max_limit ?? 200);
        const offset = payload.cursor ? Number(payload.cursor) : 0;
        const page = sorted.slice(offset, offset + limit);
        return {
          records: page.map((r) => structuredClone(r)),
          next_cursor: offset + limit < sorted.length ? String(offset + limit) : null,
        };
      },
      actionInvoke: async (_s, payload) => {
        const operationId = `run_memory_${++counter}`;
        operations.set(operationId, { state: "running" });
        const handler = actions[payload.action_id];
        setTimeout(async () => {
          const failure = failures.get(payload.action_id);
          if (failure !== undefined) {
            failures.delete(payload.action_id);
            operations.set(operationId, { state: "failed", error: { code: "operation_failed", message: failure } });
            return;
          }
          try {
            const output = await handler(payload.input, store);
            operations.set(operationId, { state: "succeeded", output });
          } catch (error) {
            operations.set(operationId, { state: "failed", error: { code: "operation_failed", message: error instanceof Error ? error.message : String(error) } });
          }
        }, latency);
        return { operation_id: operationId };
      },
      operationObserve: async (_s, payload) => {
        const op = operations.get(payload.operation_id);
        if (!op) throw new BridgeError("not_found", "unknown operation");
        return { operation_id: payload.operation_id, ...op };
      },
    },
  });
  const channel = new MessageChannel();
  const client = BridgeClient.fromPort(channel.port2, session.session_id);
  host.bind(channel.port1);
  await client.whenReady();
  return {
    client,
    host,
    store,
    failNext: (actionId, message) => failures.set(actionId, message),
    failQueries: (message) => {
      queryFailure = message;
    },
    revoke: (reason) => host.revoke(reason),
  };
}
