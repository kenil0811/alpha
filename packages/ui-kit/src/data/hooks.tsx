/**
 * Bridge-backed data for generated UI. The only way a composition reads or changes anything is
 * through its bridge session: declared read views (records.query) and declared actions
 * (action.invoke + operation.observe). Saves are never shown as stored until the platform
 * reports the action succeeded; views refresh afterwards so the UI shows committed revisions.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { BridgeClient, BridgeRequestError } from "@alpha/ui-bridge";
import { ErrorState, LoadingState, StatusMessage, type SaveState } from "../components/feedback";
import type { FilterNode, SortKey } from "./query";

export interface FieldProvenanceData {
  source: "model_estimate" | "user_correction";
  at?: string;
  call_id?: string | null;
  route?: string | null;
  model?: string | null;
  previous?: { value?: unknown; source?: string; call_id?: string | null } | null;
}

export interface RecordRow<V = Record<string, unknown>> {
  id: string;
  revision: number;
  values: V;
  provenance: Record<string, FieldProvenanceData>;
  created_at: string;
  updated_at: string;
}

export interface AggregateGroup {
  key: Record<string, unknown>;
  values: Record<string, number | string | null>;
}

/** The part of a bridge client the hooks use; BridgeClient implements it. */
export interface DataClient {
  request<T = unknown>(type: "records.query" | "action.invoke" | "operation.observe" | "artifact.open" | "input.select" | "shell.navigate", payload: Record<string, unknown>, timeoutMs?: number): Promise<T>;
  readonly revoked: string | null;
  onRevoked(listener: (reason: string) => void): () => void;
}

interface AlphaContextValue {
  client: DataClient;
  version: number;
  invalidate: () => void;
}

const AlphaContext = createContext<AlphaContextValue | null>(null);

/** Provide an already connected client (tests, the reference sheet, the memory host). */
export function AlphaProvider({ client, children }: { client: DataClient; children: ReactNode }) {
  const [version, setVersion] = useState(0);
  const invalidate = useCallback(() => setVersion((v) => v + 1), []);
  const value = useMemo(() => ({ client, version, invalidate }), [client, version, invalidate]);
  return <AlphaContext.Provider value={value}>{children}</AlphaContext.Provider>;
}

type Connection = { state: "connecting" } | { state: "ready"; client: BridgeClient } | { state: "failed"; message: string };

/**
 * Root of a generated App UI: connects to the shell over the bridge, then renders children.
 * Shows a clear state while connecting, if the connection fails, and if Alpha closes the session.
 */
export function AlphaApp({ children, timeoutMs = 10_000 }: { children: ReactNode; timeoutMs?: number }) {
  const [connection, setConnection] = useState<Connection>({ state: "connecting" });
  const [revoked, setRevoked] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    BridgeClient.connect({ timeoutMs })
      .then((client) => {
        if (cancelled) return;
        client.onRevoked((reason) => setRevoked(reason));
        setConnection({ state: "ready", client });
      })
      .catch((error: unknown) => {
        if (!cancelled) setConnection({ state: "failed", message: error instanceof Error ? error.message : String(error) });
      });
    return () => {
      cancelled = true;
    };
  }, [timeoutMs]);
  if (connection.state === "connecting") return <LoadingState label="Connecting to Alpha…" />;
  if (connection.state === "failed") {
    return <ErrorState title="This screen could not connect to Alpha" message="Close it and open it again from Alpha." />;
  }
  return (
    <AlphaProvider client={connection.client}>
      {revoked ? (
        <div className="a-connection">
          <StatusMessage tone="danger">Alpha closed this screen ({revoked}). Open it again to keep working; nothing more will be saved from here.</StatusMessage>
        </div>
      ) : null}
      <div inert={revoked ? true : undefined}>{children}</div>
    </AlphaProvider>
  );
}

export function useAlpha(): AlphaContextValue {
  const value = useContext(AlphaContext);
  if (!value) throw new Error("useAlpha must be used inside <AlphaApp> or <AlphaProvider>");
  return value;
}

/** Plain-language message for a failure: drops internal field paths such as "entries.amount". */
export function friendlyError(error: unknown): string {
  const raw = error instanceof Error ? error.message : typeof error === "string" ? error : "Something went wrong.";
  const cleaned = raw.replace(/^operation \d+ of \d+: /, "").replace(/\b[a-z][a-z0-9_]*\.([a-z][a-z0-9_]*)\b/g, "$1").replace(/_/g, " ").trim();
  const sentence = cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  return /[.!?]$/.test(sentence) ? sentence : `${sentence}.`;
}

export interface ViewQuery {
  where?: FilterNode;
  order_by?: SortKey[];
  limit?: number;
}

export interface ViewState<V> {
  records: RecordRow<V>[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
  hasNext: boolean;
  hasPrevious: boolean;
  next: () => void;
  previous: () => void;
  /** Zero-based page number. */
  page: number;
}

/** One page of a declared records view, with cursor paging. Changing the query returns to the
 *  first page; any successful action elsewhere refreshes it. */
export function useView<V = Record<string, unknown>>(view: string, query: ViewQuery = {}): ViewState<V> {
  const { client, version } = useAlpha();
  const key = JSON.stringify(query);
  const [cursors, setCursors] = useState<Array<string | null>>([null]);
  const [state, setState] = useState<{ records: RecordRow<V>[]; next: string | null; loading: boolean; error: string | null }>({
    records: [],
    next: null,
    loading: true,
    error: null,
  });
  const [reload, setReload] = useState(0);

  useEffect(() => setCursors([null]), [key, view]);

  const cursor = cursors[cursors.length - 1];
  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    const parsed = JSON.parse(key) as ViewQuery;
    client
      .request<{ records: RecordRow<V>[]; next_cursor: string | null }>("records.query", {
        view,
        ...(parsed.where ? { where: parsed.where } : {}),
        ...(parsed.order_by ? { order_by: parsed.order_by } : {}),
        ...(parsed.limit ? { limit: parsed.limit } : {}),
        ...(cursor ? { cursor } : {}),
      })
      .then((page) => {
        if (!cancelled) setState({ records: page.records, next: page.next_cursor, loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState((s) => ({ ...s, loading: false, error: friendlyError(error) }));
      });
    return () => {
      cancelled = true;
    };
  }, [client, view, key, cursor, version, reload]);

  return {
    records: state.records,
    loading: state.loading,
    error: state.error,
    refresh: () => setReload((r) => r + 1),
    hasNext: state.next !== null,
    hasPrevious: cursors.length > 1,
    next: () => {
      if (state.next) setCursors((c) => [...c, state.next]);
    },
    previous: () => setCursors((c) => (c.length > 1 ? c.slice(0, -1) : c)),
    page: cursors.length - 1,
  };
}

export interface AggregateState {
  groups: AggregateGroup[];
  truncated: boolean;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

/** A declared aggregate view (grouping and metrics fixed by the App), narrowed by a filter. */
export function useAggregate(view: string, where?: FilterNode): AggregateState {
  const { client, version } = useAlpha();
  const key = JSON.stringify(where ?? null);
  const [reload, setReload] = useState(0);
  const [state, setState] = useState<Omit<AggregateState, "refresh">>({ groups: [], truncated: false, loading: true, error: null });
  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    const filter = JSON.parse(key) as FilterNode | null;
    client
      .request<{ groups: AggregateGroup[]; truncated: boolean }>("records.query", { view, ...(filter ? { where: filter } : {}) })
      .then((result) => {
        if (!cancelled) setState({ groups: result.groups, truncated: result.truncated, loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState((s) => ({ ...s, loading: false, error: friendlyError(error) }));
      });
    return () => {
      cancelled = true;
    };
  }, [client, view, key, version, reload]);
  return { ...state, refresh: () => setReload((r) => r + 1) };
}

export class ActionFailed extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly operationId: string | null,
  ) {
    super(message);
  }
}

interface OperationSnapshot {
  operation_id: string;
  state: string;
  output?: unknown;
  error?: { code?: string; message?: string } | null;
}

const TERMINAL = new Set(["succeeded", "failed", "cancelled", "interrupted"]);

export interface ActionState<O> {
  state: SaveState;
  error: string | null;
  output: O | null;
  /** Invoke the declared action and wait for its outcome. Rejects with ActionFailed. */
  run: (input: Record<string, unknown>) => Promise<O>;
  reset: () => void;
}

/** Invoke a declared action. The promise settles only when the platform reports the outcome. */
export function useAction<O = Record<string, unknown>>(actionId: string, options: { timeoutMs?: number } = {}): ActionState<O> {
  const { client, invalidate } = useAlpha();
  const [state, setState] = useState<SaveState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [output, setOutput] = useState<O | null>(null);
  const mounted = useRef(true);
  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );
  const timeoutMs = options.timeoutMs ?? 300_000;

  const run = useCallback(
    async (input: Record<string, unknown>): Promise<O> => {
      setState("saving");
      setError(null);
      let operationId: string | null = null;
      try {
        const started = await client.request<{ operation_id: string }>("action.invoke", { action_id: actionId, input });
        operationId = started.operation_id;
        const deadline = Date.now() + timeoutMs;
        let delay = 50;
        let snapshot: OperationSnapshot | null = null;
        while (Date.now() < deadline) {
          snapshot = await client.request<OperationSnapshot>("operation.observe", { operation_id: operationId, after: 0 });
          if (TERMINAL.has(snapshot.state)) break;
          await new Promise((resolve) => setTimeout(resolve, delay));
          delay = Math.min(1000, delay * 1.5);
        }
        if (!snapshot || !TERMINAL.has(snapshot.state)) throw new ActionFailed("It is taking longer than expected. Check again later.", "timed_out", operationId);
        if (snapshot.state !== "succeeded") {
          throw new ActionFailed(
            friendlyError(snapshot.error?.message ?? `The action ${snapshot.state}.`),
            snapshot.error?.code ?? snapshot.state,
            operationId,
          );
        }
        const result = (snapshot.output ?? {}) as O;
        if (mounted.current) {
          setOutput(result);
          setState("saved");
        }
        invalidate();
        return result;
      } catch (caught) {
        const failure =
          caught instanceof ActionFailed
            ? caught
            : new ActionFailed(friendlyError(caught), caught instanceof BridgeRequestError ? caught.code : "internal", operationId);
        if (mounted.current) {
          setError(failure.message);
          setState("failed");
        }
        throw failure;
      }
    },
    [client, actionId, invalidate, timeoutMs],
  );

  const reset = useCallback(() => {
    setState("idle");
    setError(null);
  }, []);

  return { state, error, output, run, reset };
}
