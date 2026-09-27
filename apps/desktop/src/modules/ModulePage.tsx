/**
 * A module's working surface, in three fixed sections above the module's own tabs:
 *   App       the declared screen (drawn by the shell), a custom sealed screen, or action forms;
 *   Activity  what ran and what it produced, the module's automations, and what it can reach;
 *   Settings  its data, version and how it works.
 * Trusted chrome stays outside anything the module produced.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import type { AppDetail, ScheduleStatus } from "../core/client";
import { RunList } from "../components/RunList";
import type { RunView } from "../components/useRuns";
import { ActionsView } from "../workflows/ActionsView";
import { GeneratedScreen } from "../workflows/GeneratedScreen";
import { SavedData } from "../workflows/SavedData";
import { Block } from "./blocks";
import { DataSection } from "./DataSection";
import { ModuleContext, humanize, makeModuleContext, type ModuleClient } from "./useModule";

type Section = "app" | "data" | "activity" | "settings";

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
  records: { title: "Its own tables on this Mac", sub: "Only this module reads and writes them; no other module can see them." },
  models: { title: "Model estimates through your Claude subscription", sub: "What you type into an action that asks for an estimate is sent to Anthropic's Claude service. Results are labelled as estimates." },
  http: { title: "Public web pages and web search", sub: "Fetches on your behalf; nothing on this Mac or a private network, no sign-ins." },
  schedules: { title: "Runs on a timer while Alpha is open", sub: "Its schedules are listed under Automations with an on/off switch." },
  artifacts: { title: "Files it produces", sub: "Kept by Alpha; opening them from Alpha arrives in a later release." },
};

/** The module's declared schedules: on/off, last and next run, and Run now. */
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
        <h2>Automations</h2>
        <span className="faint">Run while Alpha is open on this Mac</span>
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
              ⏰
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
        {items && !items.length ? <p className="empty">This module runs nothing on its own. Everything happens when you use it.</p> : null}
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
}: {
  client: ModuleClient;
  appId: string;
  icon?: string;
  onAsk: () => void;
  /** Every run Alpha knows about; the page keeps the ones that belong to this module. */
  runs?: RunView[];
  onCancelRun?: (runId: string) => Promise<void>;
}) {
  const [detail, setDetail] = useState<AppDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [tab, setTab] = useState<string | null>(null);
  const [section, setSection] = useState<Section>("app");
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
    setSection("app");
  }, [appId]);

  const context = useMemo(() => (detail ? makeModuleContext(client, detail, version, changed) : null), [client, detail, version, changed]);
  const screen = detail?.screen ?? null;
  const currentTab = screen ? screen.tabs.find((t) => t.id === tab) ?? screen.tabs[0] : null;
  const counts = detail ? Object.values(detail.record_counts).reduce((a, b) => a + b, 0) : 0;
  const mine = useMemo(() => runs.filter((r) => (r.run.owner as { app_id?: string }).app_id === appId), [runs, appId]);
  const attention = mine.filter((r) => ["failed", "waiting_input", "waiting_approval", "waiting_connection", "needs_reconciliation"].includes(r.run.state)).length;

  const sectionTab = (key: Section, label: string, badge?: number) => (
    <button key={key} type="button" role="tab" aria-selected={section === key} onClick={() => setSection(key)}>
      {label}
      {badge ? (
        <span className="pill pill--warn" style={{ marginLeft: 6 }}>
          {badge}
        </span>
      ) : null}
    </button>
  );

  return (
    <section className="page" aria-labelledby="module-heading">
      <div className="modhead">
        <div className="modhead__title">
          <div className="modhead__ico" aria-hidden="true">
            {screen?.icon ?? icon ?? "▦"}
          </div>
          <div style={{ minWidth: 0 }}>
            <h2 id="module-heading">{detail?.name ?? "Opening…"}</h2>
            {detail ? <div className="faint">{detail.description}</div> : null}
          </div>
        </div>
        <div className="toggle toggle--sections" role="tablist" aria-label="Module sections">
          {sectionTab("app", "App")}
          {sectionTab("data", "Data")}
          {sectionTab("activity", "Activity", attention)}
          {sectionTab("settings", "Settings")}
        </div>
        <button type="button" className="btn btn--sm" onClick={onAsk}>
          Assistant
        </button>
      </div>
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
      {detail && context ? (
        <ModuleContext.Provider value={context}>
          {section === "app" ? (
            screen && currentTab ? (
              <>
                {screen.tabs.length > 1 ? (
                  <div className="subtabs" role="tablist" aria-label={`${detail.name} tabs`}>
                    {screen.tabs.map((t) => (
                      <button key={t.id} type="button" role="tab" aria-selected={currentTab.id === t.id} onClick={() => setTab(t.id)}>
                        {t.title}
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="blocks" key={currentTab.id}>
                  {groupBlocks(currentTab.blocks).map((group, i) =>
                    group.length > 1 ? (
                      <div className="chart-grid" key={`${currentTab.id}-${i}`}>
                        {group.map((block, j) => (
                          <Block key={`${currentTab.id}-${i}-${j}`} block={block} />
                        ))}
                      </div>
                    ) : (
                      <Block key={`${currentTab.id}-${i}`} block={group[0]} />
                    ),
                  )}
                </div>
              </>
            ) : detail.ui?.entry ? (
              <>
                <GeneratedScreen client={client} detail={detail} />
                <details style={{ marginTop: 16 }}>
                  <summary className="muted">Actions and saved data</summary>
                  <ActionsView client={client} appId={appId} actions={detail.actions} primary={detail.primary_action} onChanged={changed} />
                  <SavedData client={client} appId={appId} collections={detail.collections} refresh={version} />
                </details>
              </>
            ) : (
              <>
                <ActionsView client={client} appId={appId} actions={detail.actions} primary={detail.primary_action} onChanged={changed} />
                <SavedData client={client} appId={appId} collections={detail.collections} refresh={version} />
              </>
            )
          ) : null}

          {section === "data" ? (
            <>
              <div className="section__head" style={{ marginBottom: 12 }}>
                <span className="faint">
                  {counts} record{counts === 1 ? "" : "s"} across {detail.collections.length} table{detail.collections.length === 1 ? "" : "s"} · {detail.data_notice ?? "Its records stay on this Mac."} · Changes you make here are kept as yours.
                </span>
              </div>
              <DataSection client={client} detail={detail} version={version} onChanged={changed} />
            </>
          ) : null}

          {section === "activity" ? (
            <>
              <div className="section" style={{ marginTop: 0 }}>
                <div className="section__head">
                  <h2>What ran</h2>
                  <span className="faint">Every action of this module, newest first, with its outcome</span>
                </div>
                {onCancelRun ? <RunList runs={mine} onCancel={onCancelRun} appNames={{ [appId]: detail.name }} /> : <p className="empty">Nothing has run yet.</p>}
              </div>
              <Automations client={client} appId={appId} version={version} onChanged={changed} />
              <div className="section">
                <div className="section__head">
                  <h2>What it can reach</h2>
                </div>
                <div className="card list">
                  {(detail.capabilities ?? []).map((family) => {
                    const words = ACCESS[family] ?? { title: humanize(family), sub: "" };
                    return (
                      <div className="item" key={family}>
                        <div className="item__ico" aria-hidden="true">
                          ●
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
                      ○
                    </div>
                    <div className="item__body">
                      <b>Nothing else</b>
                      <div className="item__sub">No files on this Mac, no other module's data, no sign-ins, no messages. {detail.data_notice ?? "Its records stay on this Mac."}</div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          ) : null}

          {section === "settings" ? (
            <>
              <div className="section" style={{ marginTop: 0 }}>
                <div className="section__head">
                  <h2>How it works</h2>
                </div>
                <div className="card list">
                  <div className="item">
                    <div className="item__ico" aria-hidden="true">
                      ⚙
                    </div>
                    <div className="item__body">
                      <b>What it can do</b>
                      <div className="item__sub">{detail.actions.map((a) => `${a.title}: ${a.description}`).join(" · ")}</div>
                    </div>
                  </div>
                  {screen?.assistant_hint ? (
                    <div className="item">
                      <div className="item__ico" aria-hidden="true">
                        💬
                      </div>
                      <div className="item__body">
                        <b>What the assistant knows about it</b>
                        <div className="item__sub">{screen.assistant_hint}</div>
                      </div>
                    </div>
                  ) : null}
                  <div className="item">
                    <div className="item__ico" aria-hidden="true">
                      🕘
                    </div>
                    <div className="item__body">
                      <b>Version</b>
                      <div className="item__sub" title={`Version ${detail.version_id} · runtime ${detail.runtime_profile_id}`}>
                        Built by Alpha · the current version is in use
                      </div>
                    </div>
                    <span className="faint">Changes arrive in a later release</span>
                  </div>
                </div>
              </div>
            </>
          ) : null}
        </ModuleContext.Provider>
      ) : null}
    </section>
  );
}
