/**
 * A module's working surface, Bridge anatomy: a 56px header carrying the module's own page tabs,
 * the page itself, then below the fold Intelligence (automations and what ran), Governance (what
 * it can reach, its connections and sign-ins) and the module's settings (how it works, version,
 * remove). Trusted chrome stays outside anything the module produced.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlarmClock, ArrowLeftRight, Ban, Boxes, Check, Cog, History, icons as lucideIcons, MessageSquare, Settings2, ShieldCheck, Sparkles, Trash2, type LucideIcon } from "lucide-react";
import { Badge, InfoTip, Tabs } from "../ui";
import { ZazooIcon } from "../ui/ZazooIcon";
import "./module.css";
import { checksOwed, type AppChecks, type AppDetail, type BrowserAccess, type BrowserVisit, type ModuleConnection, type ScheduleStatus, isConnectionsClient } from "../core/client";
import { ChecksNotice } from "../workflows/ChecksNotice";
import { RunList } from "../components/RunList";
import type { RunView } from "../components/useRuns";
import { ActionsView } from "../workflows/ActionsView";
import { GeneratedScreen } from "../workflows/GeneratedScreen";
import { Block } from "./blocks";
import { DataPage } from "./DataPage";
import type { ModuleFailure } from "../core/client";
import { ModuleContext, humanize, makeModuleContext, type ModuleClient } from "./useModule";

export type Section = "app" | "activity" | "settings";
/** id of the below-the-fold section each route `section` value scrolls to; "app" scrolls to top. */
const SECTION_ANCHOR: Record<Section, string | null> = { app: null, activity: "mod-intelligence", settings: "mod-governance" };

function resolveIcon(name?: string | null): LucideIcon {
  if (!name) return Boxes;
  const pascal = name.replace(/(^\w|-\w)/g, (t) => t.replace("-", "").toUpperCase());
  return (lucideIcons as Record<string, LucideIcon>)[pascal] ?? Boxes;
}

/** The tabs a module shows: its summary, any declared screen tabs, then one page per table. */
type PageTab =
  | { id: string; title: string; kind: "summary" }
  | { id: string; title: string; kind: "ui" }
  | { id: string; title: string; kind: "screen"; index: number }
  | { id: string; title: string; kind: "collection"; name: string }
  | { id: string; title: string; kind: "actions" };

export function moduleTabs(detail: AppDetail): PageTab[] {
  const tabs: PageTab[] = [];
  if (detail.summary?.length) tabs.push({ id: "summary", title: "Summary", kind: "summary" });
  if (detail.ui?.entry) tabs.push({ id: "ui", title: "Screen", kind: "ui" });
  (detail.screen?.tabs ?? []).forEach((t, index) => tabs.push({ id: `screen:${t.id}`, title: t.title, kind: "screen", index }));
  // A declared screen tab that already lists a table (a table, board or list over one of its
  // views) covers that table; the derived page steps aside so nothing shows twice.
  const viewCollection = new Map((detail.views ?? []).map((v) => [v.id, v.collection]));
  const covered = new Set<string>();
  for (const tab of detail.screen?.tabs ?? []) {
    for (const block of tab.blocks) {
      if (block.kind === "table" || block.kind === "board" || block.kind === "list") {
        const collection = viewCollection.get(block.view);
        if (collection) covered.add(collection);
      }
    }
  }
  for (const c of detail.collections) if (!covered.has(c.name)) tabs.push({ id: `page:${c.name}`, title: humanize(c.name), kind: "collection", name: c.name });
  // Actions a person runs by hand get a tab when no declared screen already offers them.
  const manual = detail.actions.some((a) => a.invocable_from.includes("manual"));
  if (manual && !detail.screen) tabs.push({ id: "actions", title: "Actions", kind: "actions" });
  return tabs;
}

/** Runs of charts sit side by side instead of one tall card each. */
function groupBlocks<T extends { kind: string }>(blocks: T[]): T[][] {
  const groups: T[][] = [];
  for (const block of blocks) {
    const last = groups[groups.length - 1];
    if (block.kind === "trend" && last && last[0].kind === "trend") last.push(block);
    else groups.push([block]);
  }
  return groups;
}

function when(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  const sameDay = date.toDateString() === new Date().toDateString();
  return sameDay ? date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : date.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** What a capability family means for the person, in plain words. */
const ACCESS: Record<string, { title: string; sub: string }> = {
  records: { title: "Its own tables on this Mac", sub: "Only this project reads and writes them; no other project can see them." },
  models: { title: "Model estimates through your Claude subscription", sub: "What you type into an action that asks for an estimate is sent to Anthropic's Claude service. Results are labelled as estimates." },
  http: { title: "Public web pages and web search", sub: "Fetches on your behalf; nothing on this Mac or a private network, no sign-ins." },
  schedules: { title: "Runs on a timer while Alpha is open", sub: "Its schedules are listed under Automations with an on/off switch." },
  browser: { title: "Your signed-in browser, when you allow it", sub: "Reads sites you signed into on Connections, only for the sites switched on in this project's Settings. Read-only and paced; every page is listed above." },
  artifacts: { title: "Files it produces", sub: "Kept by Alpha; opening them from Alpha arrives in a later release." },
  profile: { title: "What Alpha knows about you", sub: "Reads the facts on your About you page and passes on what you tell it; anything it works out waits there for your yes." },
  connections: { title: "Other projects' data, read-only", sub: "Reads what the projects listed under Settings keep, through the views they declare. Each one has a switch." },
};

/** What this module reads from other modules, with the person's switch on each. */
function ConnectionSwitches({ client, appId }: { client: ModuleClient; appId: string }) {
  const [rows, setRows] = useState<ModuleConnection[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!isConnectionsClient(client)) return;
    let cancelled = false;
    client
      .connections(appId)
      .then((all) => {
        if (!cancelled) setRows(all);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [client, appId]);
  if (!isConnectionsClient(client) || !rows?.length) return null;
  const toggle = async (row: ModuleConnection) => {
    try {
      setRows(await client.setConnection(appId, row.module, !row.enabled));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  return (
    <div className="section" style={{ marginTop: 0 }}>
      <div className="section__head">
        <h2>
          Reads from other projects
          <InfoTip content="Read-only, through the views those projects declare. Switch any off; the project then says it cannot read it." label="About reading other projects" />
        </h2>
      </div>
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
      <div className="card list" aria-label="Connections">
        {rows.map((row) => (
          <div className="item" key={row.module}>
            <div className="item__ico" aria-hidden="true">
              <ArrowLeftRight size={16} />
            </div>
            <div className="item__body">
              <b>{row.name}</b>
              <div className="item__sub">
                {row.purpose} · {row.views.map((v) => v.collection ?? v.id).join(", ")}
                {row.installed ? "" : " · not installed right now"}
              </div>
            </div>
            <button type="button" className={`btn btn--sm${row.enabled ? " btn--primary" : ""}`} aria-pressed={row.enabled} onClick={() => void toggle(row)}>
              {row.enabled ? "On" : "Off"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

/** The fast lane's follow-up on the module's own page: its behaviour checks, while they run
 *  and when they land, with the one click back when they find a problem. */
function ChecksBanner({ client, appId, releaseId, onReverted, onRemoved }: { client: ModuleClient; appId: string; releaseId: string; onReverted: () => void; onRemoved?: () => void }) {
  const [checks, setChecks] = useState<AppChecks | null>(null);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const load = () => {
      client
        .appChecks(appId)
        .then((next) => {
          if (cancelled) return;
          setChecks(next);
          if (checksOwed(next)) timer = setTimeout(load, 3000);
        })
        .catch(() => undefined);
    };
    load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [client, appId, releaseId]);
  // Only the checks of the version in use are the person's business here.
  if (!checks || checks.status === "passed" || (checks.release_id && checks.release_id !== releaseId)) return null;
  return (
    <div className="card" style={{ padding: 10, marginBottom: 12 }} aria-label="Behaviour checks">
      <ChecksNotice checks={checks} client={client} appId={appId} changeOf={checks.change_of} releaseId={checks.release_id} onReverted={onReverted} onRemoved={onRemoved} />
    </div>
  );
}

/** The module's declared schedules: on/off, last and next run, and Run now. */
/** Which signed-in sites this module may read through: off until the person switches it on. */
function BrowserAccessSwitches({ client, appId }: { client: ModuleClient; appId: string }) {
  const [rows, setRows] = useState<BrowserAccess[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    client.browserAccess(appId).then(setRows).catch(() => setRows([]));
  }, [client, appId]);
  async function toggle(site: string, on: boolean) {
    if (!rows) return;
    const next = rows.filter((r) => (r.site === site ? on : r.allowed)).map((r) => r.site);
    try {
      setRows(await client.setBrowserAccess(appId, next));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  if (!rows) return null;
  return (
    <div className="section">
      <div className="section__head">
        <h2>
          Your signed-in browser
          <InfoTip content="Sites you signed into on Connections. Reading only, paced, every page listed under Activity." label="About signed-in browser access" />
        </h2>
      </div>
      <div className="card list" aria-label="Signed-in browser access">
        {rows.length === 0 ? <p className="empty">No sites yet. Sign in to one on Connections first.</p> : null}
        {rows.map((r) => (
          <div className="item" key={r.site}>
            <div className="item__body">
              <b>{r.site}</b>
              <div className="item__sub">{r.state === "connected" ? (r.allowed ? "This project may read through your session." : "Off: this project reads it as a visitor.") : "Not signed in."}</div>
            </div>
            <label className="switch">
              <input type="checkbox" checked={r.allowed} disabled={r.state !== "connected"} onChange={(e) => void toggle(r.site, e.target.checked)} aria-label={`Allow ${r.site}`} />
              <span />
            </label>
          </div>
        ))}
      </div>
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** Pages this module opened through the person's browser, newest first. */
function BrowserVisits({ client, appId, version }: { client: ModuleClient; appId: string; version: number }) {
  const [rows, setRows] = useState<BrowserVisit[]>([]);
  useEffect(() => {
    client.browserVisits(appId).then(setRows).catch(() => setRows([]));
  }, [client, appId, version]);
  if (!rows.length) return null;
  return (
    <div className="section">
      <div className="section__head">
        <h2>
          Pages opened in your browser
          <InfoTip content="Through your signed-in session or a rendered page, newest first." label="About pages opened" />
        </h2>
      </div>
      <div className="card list" aria-label="Pages opened in your browser">
        {rows.map((v) => (
          <div className="item" key={v.visit_id}>
            <div className="item__body">
              <b>{v.url.replace(/^https?:\/\//, "").slice(0, 90)}</b>
              <div className="item__sub">
                {when(v.at)} · {v.signed_in ? "your session" : "as a visitor"}
                {v.blocked ? " · the site asked to sign in" : ""}
                {v.status ? ` · ${v.status}` : ""}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Automations({ client, appId, version, onChanged }: { client: ModuleClient; appId: string; version: number; onChanged: () => void }) {
  const [items, setItems] = useState<ScheduleStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!client.listSchedules) return;
    let cancelled = false;
    client
      .listSchedules(appId)
      .then((all) => {
        if (!cancelled) setItems(all);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [client, appId, version]);
  const act = (promise: Promise<ScheduleStatus[]>, ran = false) =>
    promise
      .then((next) => {
        setItems(next);
        // A run just started: give it a moment, then let the blocks reload what it saved.
        if (ran) window.setTimeout(onChanged, 2500);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  return (
    <div className="section">
      <div className="section__head">
        <h2>
          Automations
          <InfoTip content="Run while Alpha is open on this Mac." label="About automations" />
        </h2>
      </div>
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
      <div className="card list">
        {(items ?? []).map((s) => (
          <div className="item" key={s.id}>
            <div className="item__ico" aria-hidden="true">
              <AlarmClock size={16} />
            </div>
            <div className="item__body">
              <b>{s.title}</b>
              <div className="item__sub">
                {s.when[0].toUpperCase() + s.when.slice(1)}
                {s.last_run_at ? ` · last ran ${when(s.last_run_at)}` : " · has not run yet"}
                {s.enabled && s.next_run_at ? ` · next ${when(s.next_run_at)}` : s.enabled ? "" : " · off"}
                {s.last_error ? ` · last time: ${s.last_error}` : ""}
              </div>
            </div>
            <button type="button" className="btn btn--sm" onClick={() => client.runSchedule && act(client.runSchedule(appId, s.id), true)}>
              Run now
            </button>
            <button
              type="button"
              className={s.enabled ? "switch" : "switch switch--off"}
              role="switch"
              aria-checked={s.enabled}
              aria-label={`${s.title} ${s.enabled ? "on" : "off"}`}
              onClick={() => client.setSchedule && act(client.setSchedule(appId, s.id, !s.enabled))}
            />
          </div>
        ))}
        {items && !items.length ? <p className="empty">This project runs nothing on its own. Everything happens when you use it.</p> : null}
      </div>
    </div>
  );
}

/** What went wrong lately, whose fault it was, and what Alpha did about it on its own. */
function Failures({ client, appId, version }: { client: ModuleClient; appId: string; version: number }) {
  const [items, setItems] = useState<ModuleFailure[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    client
      .appRepairs(appId)
      .then((found) => {
        if (!cancelled) setItems(found.failures);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [client, appId, version]);
  if (!items?.length) return null;
  const word = (f: ModuleFailure) =>
    f.repair ? (f.repair.state === "fixed" ? "Fixed" : f.repair.state === "fixing" ? "Fixing" : "Not fixed") : f.kind === "module_code" ? "Alpha will fix this" : f.kind === "refusal" ? "Refused" : f.kind === "outside" ? "Outside Alpha" : "Alpha's own problem";
  return (
    <div className="section">
      <div className="section__head">
        <h2>
          What went wrong
          <InfoTip content="Recent failures in plain words, and what Alpha did about them." label="About failures" />
        </h2>
      </div>
      <div className="card list" aria-label="What went wrong">
        {items.map((f) => (
          <div className="item" key={f.run_id}>
            <span className={`pill ${f.repair?.state === "fixed" ? "pill--good" : f.repair?.state === "fixing" ? "pill--info" : f.kind === "module_code" ? "pill--warn" : "pill--gray"}`}>{word(f)}</span>
            <div className="item__body">
              <div>{f.said}</div>
              <div className="item__sub">
                {new Date(f.at).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                {f.repair ? ` · ${f.repair.summary}` : ""}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ModulePage({
  client,
  appId,
  icon,
  onAsk,
  runs = [],
  onCancelRun,
  onRemoved,
  section: routedSection,
}: {
  client: ModuleClient;
  appId: string;
  icon?: LucideIcon;
  onAsk: () => void;
  /** Every run Alpha knows about; the page keeps the ones that belong to this module. */
  runs?: RunView[];
  onCancelRun?: (runId: string) => Promise<void>;
  /** The module was taken out of use from this page; the shell leaves it. */
  onRemoved?: () => void;
  /** Section from the route (#/m/:id/:section): the page scrolls to it. */
  section?: Section;
  onSectionChange?: (section: Section) => void;
}) {
  const [goingBack, setGoingBack] = useState<"ask" | "busy" | string | null>(null);
  const [removing, setRemoving] = useState<"ask" | "busy" | string | null>(null);
  const removeModule = async () => {
    setRemoving("busy");
    try {
      await client.removeApp(appId, detail?.release_id ?? null);
      onRemoved?.();
    } catch (e) {
      setRemoving(e instanceof Error ? e.message : String(e));
    }
  };
  const goBack = async () => {
    setGoingBack("busy");
    try {
      await client.revertApp(appId, detail?.release_id ?? null);
      setGoingBack("Back on the previous version. Your records are kept.");
      changed();
    } catch (e) {
      setGoingBack(e instanceof Error ? e.message : String(e));
    }
  };
  const [detail, setDetail] = useState<AppDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [tab, setTab] = useState<string | null>(null);
  const [intelTab, setIntelTab] = useState<"runs" | "automations">("runs");
  const section = routedSection ?? "app";
  const changed = useCallback(() => setVersion((n) => n + 1), []);

  useEffect(() => {
    setError(null);
    client
      .appDetail(appId)
      .then(setDetail)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [client, appId, version]);
  useEffect(() => {
    setDetail(null);
    setTab(null);
  }, [appId]);
  useEffect(() => {
    if (!detail) return;
    if (section === "activity") setIntelTab("runs");
    const anchor = SECTION_ANCHOR[section];
    if (anchor) document.getElementById(anchor)?.scrollIntoView({ block: "start" });
  }, [section, detail]);

  const context = useMemo(() => (detail ? makeModuleContext(client, detail, version, changed) : null), [client, detail, version, changed]);
  const screen = detail?.screen ?? null;
  const tabs = useMemo(() => (detail ? moduleTabs(detail) : []), [detail]);
  const currentTab = tabs.find((t) => t.id === tab) ?? tabs[0] ?? null;
  const screenTab = currentTab?.kind === "screen" && screen ? screen.tabs[currentTab.index] : null;
  const pageCollection = currentTab?.kind === "collection" && detail ? detail.collections.find((c) => c.name === currentTab.name) : null;
  const mine = useMemo(() => runs.filter((r) => (r.run.owner as { app_id?: string }).app_id === appId), [runs, appId]);
  const HeadIcon = screen?.icon ? resolveIcon(screen.icon) : icon ?? Boxes;
  const attention = mine.filter((r) => ["failed", "waiting_input", "waiting_approval", "waiting_connection", "needs_reconciliation"].includes(r.run.state)).length;

  return (
    <section className="page mod-page" aria-labelledby="module-heading">
      <header className="modhead">
        <div className="modhead__title">
          <div className="modhead__ico" aria-hidden="true">
            <HeadIcon size={18} strokeWidth={1.75} />
          </div>
          <h2 id="module-heading">
            {detail?.name ?? "Opening…"}
            {detail?.description ? <InfoTip content={detail.description} label={`About ${detail.name}`} /> : null}
          </h2>
        </div>
        {tabs.length > 1 ? (
          <Tabs className="modhead__tabs" items={tabs.map((t) => ({ value: t.id, label: t.title }))} value={currentTab?.id ?? tabs[0].id} onChange={setTab} aria-label={`${detail?.name ?? "Project"} tabs`} />
        ) : null}
        <button type="button" className="btn btn--sm modhead__assist" onClick={onAsk}>
          <ZazooIcon size={18} label="" />
          Chief of Staff
        </button>
      </header>
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
      {detail && context ? (
        <ModuleContext.Provider value={context}>
          <ChecksBanner client={client} appId={appId} releaseId={detail.release_id} onReverted={changed} onRemoved={onRemoved} />
          <div className="mod-app" id="mod-app">
          {(
            tabs.length ? (
              <>
                {currentTab?.kind === "summary" ? (
                  <div className="blocks" key="summary">
                    {groupBlocks(detail.summary ?? []).map((group, i) =>
                      group.length > 1 ? (
                        <div className="chart-grid" key={`summary-${i}`}>
                          {group.map((block, j) => (
                            <Block key={`summary-${i}-${j}`} block={block} position={i} />
                          ))}
                        </div>
                      ) : (
                        <Block key={`summary-${i}`} block={group[0]} position={i} />
                      ),
                    )}
                  </div>
                ) : null}
                {screenTab ? (
                  <div className="blocks" key={screenTab.id}>
                    {groupBlocks(screenTab.blocks).map((group, i) =>
                      group.length > 1 ? (
                        <div className="chart-grid" key={`${screenTab.id}-${i}`}>
                          {group.map((block, j) => (
                            <Block key={`${screenTab.id}-${i}-${j}`} block={block} position={i} />
                          ))}
                        </div>
                      ) : (
                        <Block key={`${screenTab.id}-${i}`} block={group[0]} position={i} />
                      ),
                    )}
                  </div>
                ) : null}
                {pageCollection ? <DataPage key={pageCollection.name} collection={pageCollection} /> : null}
                {currentTab?.kind === "ui" ? <GeneratedScreen client={client} detail={detail} /> : null}
                {currentTab?.kind === "actions" ? <ActionsView client={client} appId={appId} actions={detail.actions} primary={detail.primary_action} onChanged={changed} /> : null}
              </>
            ) : (
              <ActionsView client={client} appId={appId} actions={detail.actions} primary={detail.primary_action} onChanged={changed} />
            )
          )}
          </div>

          <div className="mod-sections">
            <section className="mod-section" id="mod-intelligence" aria-labelledby="mod-intelligence-title">
              <h2 className="mod-section__title" id="mod-intelligence-title">
                <Sparkles size={16} aria-hidden="true" /> Intelligence
              </h2>
              <Tabs
                aria-label="Intelligence"
                value={intelTab}
                onChange={(v) => setIntelTab(v as typeof intelTab)}
                items={[
                  { value: "runs", label: <>What ran {mine.length ? <Badge variant={attention ? "warning" : "neutral"}>{attention || mine.length}</Badge> : null}</> },
                  { value: "automations", label: "Automations" },
                ]}
              />
              {intelTab === "runs" ? (
                <div style={{ marginTop: 12 }}>
                  {onCancelRun ? <RunList runs={mine} onCancel={onCancelRun} appNames={{ [appId]: detail.name }} /> : <p className="empty">Nothing has run yet.</p>}
                  {(detail.capabilities ?? []).includes("browser") ? <BrowserVisits client={client} appId={appId} version={version} /> : null}
                  <Failures client={client} appId={appId} version={version} />
                </div>
              ) : (
                <Automations client={client} appId={appId} version={version} onChanged={changed} />
              )}
            </section>

            <section className="mod-section" id="mod-governance" aria-labelledby="mod-governance-title">
              <h2 className="mod-section__title" id="mod-governance-title">
                <ShieldCheck size={16} aria-hidden="true" /> Governance
              </h2>
              <div className="section" style={{ marginTop: 0 }}>
                <div className="section__head">
                  <h2>What it can reach</h2>
                </div>
                <div className="card list">
                  {(detail.capabilities ?? []).map((family) => {
                    const words = ACCESS[family] ?? { title: humanize(family), sub: "" };
                    return (
                      <div className="item" key={family}>
                        <div className="item__ico" aria-hidden="true">
                          <Check size={16} />
                        </div>
                        <div className="item__body">
                          <b>{words.title}</b>
                          <div className="item__sub">{words.sub}</div>
                        </div>
                      </div>
                    );
                  })}
                  <div className="item">
                    <div className="item__ico" aria-hidden="true">
                      <Ban size={16} />
                    </div>
                    <div className="item__body">
                      <b>Nothing else</b>
                      <div className="item__sub">No files on this Mac, no other project's data, no sign-ins, no messages. {detail.data_notice ?? "Its records stay on this Mac."}</div>
                    </div>
                  </div>
                </div>
              </div>
              {(detail.uses ?? []).length ? <ConnectionSwitches client={client} appId={appId} /> : null}
              {(detail.capabilities ?? []).includes("browser") ? <BrowserAccessSwitches client={client} appId={appId} /> : null}
              <p className="item__sub">Changes to what it can reach happen through the Chief of Staff.</p>
            </section>

            <section className="mod-section" id="mod-settings" aria-labelledby="mod-settings-title">
              <h2 className="mod-section__title" id="mod-settings-title">
                <Settings2 size={16} aria-hidden="true" /> Settings
              </h2>
              <div className="section" style={{ marginTop: 0 }}>
                <div className="section__head">
                  <h2>How it works</h2>
                </div>
                <div className="card list">
                  <div className="item">
                    <div className="item__ico" aria-hidden="true">
                      <Cog size={16} />
                    </div>
                    <div className="item__body">
                      <b>What it can do</b>
                      <div className="item__sub">{detail.actions.map((a) => `${a.title}: ${a.description}`).join(" · ")}</div>
                    </div>
                  </div>
                  {screen?.assistant_hint ? (
                    <div className="item">
                      <div className="item__ico" aria-hidden="true">
                        <MessageSquare size={16} />
                      </div>
                      <div className="item__body">
                        <b>What the assistant knows about it</b>
                        <div className="item__sub">{screen.assistant_hint}</div>
                      </div>
                    </div>
                  ) : null}
                  <div className="item">
                    <div className="item__ico" aria-hidden="true">
                      <History size={16} />
                    </div>
                    <div className="item__body">
                      <b>Version</b>
                      <div className="item__sub" title={`Version ${detail.version_id} · runtime ${detail.runtime_profile_id}`}>
                        Built by Alpha · the current version is in use
                        {typeof goingBack === "string" && goingBack !== "ask" && goingBack !== "busy" ? ` · ${goingBack}` : ""}
                      </div>
                    </div>
                    {detail.can_revert ? (
                      goingBack === "ask" ? (
                        <span className="row" style={{ gap: 6 }}>
                          <span className="faint">Go back? Your records stay.</span>
                          <button type="button" className="btn btn--sm btn--primary" onClick={() => void goBack()}>
                            Go back
                          </button>
                          <button type="button" className="btn btn--sm" onClick={() => setGoingBack(null)}>
                            Cancel
                          </button>
                        </span>
                      ) : (
                        <button type="button" className="btn btn--sm" disabled={goingBack === "busy"} onClick={() => setGoingBack("ask")}>
                          Go back to the previous version
                        </button>
                      )
                    ) : (
                      <span className="faint">Changes arrive in a later release</span>
                    )}
                  </div>
                </div>
              </div>
              <div className="section">
                <div className="section__head">
                  <h2>Remove</h2>
                </div>
                <div className="card list">
                  <div className="item">
                    <div className="item__ico" aria-hidden="true">
                      <Trash2 size={16} />
                    </div>
                    <div className="item__body">
                      <b>Remove this project</b>
                      <div className="item__sub">Deletes the project and everything that exists because of it: its records, its history of runs and changes, and what was said about it in the assistant. This cannot be undone.</div>
                      {typeof removing === "string" && removing !== "ask" && removing !== "busy" ? (
                        <p className="notice" role="alert">
                          {removing}
                        </p>
                      ) : null}
                    </div>
                    {removing === "ask" ? (
                      <span className="row" style={{ gap: 6 }}>
                        <span className="faint">Remove {detail.name} and all its data?</span>
                        <button type="button" className="btn btn--sm btn--danger" onClick={() => void removeModule()}>
                          Remove
                        </button>
                        <button type="button" className="btn btn--sm" onClick={() => setRemoving(null)}>
                          Cancel
                        </button>
                      </span>
                    ) : (
                      <button type="button" className="btn btn--sm" disabled={removing === "busy"} onClick={() => setRemoving("ask")}>
                        Remove this project
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </section>
          </div>
        </ModuleContext.Provider>
      ) : null}
    </section>
  );
}
