/**
 * One module's data access for the declarative screen: query its declared views, run its
 * actions and tell every block when something changed so it reloads. Core enforces the views
 * (filterable/sortable fields, limits) and validates every action input again.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ActionSummary, AggregateResultPage, AppDetail, AppsClient, DeclaredView, FilterNode, OperationOutcome, RecordPageResult, WorkflowsClient } from "../core/client";
import { runAndWait } from "../workflows/ActionsView";

export type ModuleClient = WorkflowsClient & AppsClient;

export interface ModuleContextValue {
  client: ModuleClient;
  detail: AppDetail;
  /** Bumps after every successful action; blocks reload their views when it changes. */
  version: number;
  changed: () => void;
  view: (viewId: string) => DeclaredView | undefined;
  action: (actionId: string) => ActionSummary | undefined;
  /** Run an action and wait for its outcome. Resolves for any final state; throws only when
   *  Core could not be asked. */
  run: (actionId: string, input: Record<string, unknown>) => Promise<OperationOutcome>;
}

export const ModuleContext = createContext<ModuleContextValue | null>(null);

export function useModule(): ModuleContextValue {
  const value = useContext(ModuleContext);
  if (!value) throw new Error("useModule outside a module");
  return value;
}

export function makeModuleContext(client: ModuleClient, detail: AppDetail, version: number, changed: () => void): ModuleContextValue {
  const views = new Map<string, DeclaredView>();
  for (const v of detail.views ?? []) views.set(v.id, v);
  for (const v of detail.ui?.views ?? []) if (!views.has(v.id)) views.set(v.id, v as unknown as DeclaredView);
  const actions = new Map(detail.actions.map((a) => [a.id, a]));
  return {
    client,
    detail,
    version,
    changed,
    view: (id) => views.get(id),
    action: (id) => actions.get(id),
    run: async (actionId, input) => {
      const action = actions.get(actionId);
      if (!action) throw new Error(`This module has no action ${actionId}`);
      const outcome = await runAndWait(client, detail.app_id, action, input);
      if (outcome.state === "succeeded") changed();
      return outcome;
    },
  };
}

export interface ViewQueryBody {
  where?: FilterNode | null;
  order_by?: { field: string; direction: "asc" | "desc" }[];
  limit?: number;
  cursor?: string | null;
}

interface QueryState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

/** Query a declared view; reloads whenever the body or the module's data version changes. */
export function useViewQuery<T = RecordPageResult | AggregateResultPage>(viewId: string | null, body: ViewQueryBody): QueryState<T> & { reload: () => void } {
  const { client, detail, version } = useModule();
  const [state, setState] = useState<QueryState<T>>({ data: null, loading: Boolean(viewId), error: null });
  const [tick, setTick] = useState(0);
  const key = useMemo(() => JSON.stringify(body), [body]);
  const latest = useRef(0);
  useEffect(() => {
    if (!viewId) return;
    const mine = ++latest.current;
    setState((s) => ({ ...s, loading: true }));
    client
      .queryView(detail.app_id, viewId, JSON.parse(key) as Record<string, unknown>)
      .then((data) => {
        if (mine === latest.current) setState({ data: data as T, loading: false, error: null });
      })
      .catch((e: unknown) => {
        if (mine === latest.current) setState({ data: null, loading: false, error: e instanceof Error ? e.message : String(e) });
      });
  }, [client, detail.app_id, viewId, key, version, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}

/** Today's date in the person's local time as YYYY-MM-DD. */
export function todayDay(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function shiftDay(day: string, byDays: number): string {
  const [y, m, d] = day.split("-").map(Number);
  const date = new Date(y, m - 1, d + byDays);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function humanize(name: string): string {
  const words = name.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function formatNumber(value: number, unit?: string | null): string {
  const text = Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 1 });
  return unit ? `${text} ${unit}` : text;
}

export function formatDay(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  if (!y || !m || !d) return day;
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/** The words Core's outcome carries for a person: the output's own message when it has one. */
export function outcomeWords(outcome: OperationOutcome, fallback = "Done."): { ok: boolean; text: string } {
  if (outcome.state === "succeeded") {
    const out = outcome.output as Record<string, unknown> | null;
    const message = out && typeof out.message === "string" ? out.message : out && typeof out.summary === "string" ? out.summary : null;
    return { ok: true, text: message ?? fallback };
  }
  if (outcome.state === "cancelled") return { ok: false, text: "You stopped it." };
  return { ok: false, text: outcome.error?.message ?? `It ${outcome.state}.` };
}
