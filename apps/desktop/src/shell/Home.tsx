import type { Run } from "@alpha/contracts";
import { Boxes, type LucideIcon } from "lucide-react";
import type { AppSummary } from "../core/client";

const ATTENTION = new Set(["waiting_input", "waiting_approval", "waiting_connection", "needs_reconciliation", "failed"]);

function greeting(): string {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

function ago(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function Home({
  modules,
  icons,
  runs,
  onOpen,
  onNew,
  onActivity,
}: {
  modules: AppSummary[];
  icons: Record<string, LucideIcon>;
  runs: Run[];
  onOpen: (appId: string) => void;
  onNew: () => void;
  onActivity: () => void;
}) {
  const today = new Date();
  const startOfDay = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const ranToday = runs.filter((r) => new Date(r.created_at).getTime() >= startOfDay);
  const attention = runs.filter((r) => ATTENTION.has(r.state));
  const lastRunByApp = new Map<string, Run>();
  for (const run of runs) {
    const owner = run.owner as { app_id?: string };
    if (owner.app_id && !lastRunByApp.has(owner.app_id)) lastRunByApp.set(owner.app_id, run);
  }
  return (
    <section className="page" aria-labelledby="home-heading">
      <div className="eyebrow">{today.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}</div>
      <h1 id="home-heading" style={{ marginTop: 6 }}>
        {greeting()}
      </h1>
      <div className="today">
        <div className="card tile">
          <div className="tile__lab">Modules</div>
          <div className="tile__big num">{modules.length}</div>
          <div className="tile__sub">{modules.length ? "Ready to use on this Mac" : "Describe what you want to make the first one"}</div>
        </div>
        <div className="card tile">
          <div className="tile__lab">Ran today</div>
          <div className="tile__big num">{ranToday.length}</div>
          <div className="tile__sub">{ranToday.length ? `${ranToday.filter((r) => r.state === "succeeded").length} finished fine` : "Nothing has run yet today"}</div>
        </div>
        <div className="card tile">
          <div className="tile__lab">Needs you</div>
          <div className="tile__big num">{attention.length}</div>
          <div className="tile__sub">
            {attention.length ? (
              <button type="button" className="btn btn--sm" onClick={onActivity}>
                See what
              </button>
            ) : (
              "Nothing is waiting on you"
            )}
          </div>
        </div>
      </div>
      <div className="section" style={{ marginTop: 0 }}>
        <div className="section__head">
          <h2>Your modules</h2>
          <div className="section__right">
            <button type="button" className="btn btn--sm" onClick={onActivity}>
              See all activity
            </button>
          </div>
        </div>
        <div className="modgrid">
          {modules.map((m) => {
            const last = lastRunByApp.get(m.app_id);
            const Icon = icons[m.app_id] ?? Boxes;
            return (
              <div className="card modcard" key={m.app_id}>
                <div className="modcard__top">
                  <div className="modcard__ico" aria-hidden="true">
                    <Icon size={18} strokeWidth={1.75} />
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <b>{m.name}</b>
                    <div className="faint">{m.has_ui ? "Has its own screen" : `${m.actions} action${m.actions === 1 ? "" : "s"}`}</div>
                  </div>
                  <span className={`pill ${m.state === "active" ? "pill--good" : "pill--gray"}`} style={{ marginLeft: "auto" }}>
                    {m.state === "active" ? "Active" : m.state}
                  </span>
                </div>
                <p>{m.description}</p>
                <div className="modcard__foot">
                  <span>{last ? `Last ran ${ago(last.created_at)}` : `Made ${ago(m.created_at)}`}</span>
                  <button type="button" className="btn btn--sm" aria-label={`Open ${m.name}`} onClick={() => onOpen(m.app_id)}>
                    Open
                  </button>
                </div>
              </div>
            );
          })}
          <div className="card modcard modcard--new">
            <div className="eyebrow">New</div>
            <b>Describe what you want</b>
            <p>
              “Track what I eat”, “Watch a page for price drops”, “Turn my receipts into a monthly summary”. Alpha asks a couple of questions,
              then builds it here.
            </p>
            <button type="button" className="link" onClick={onNew}>
              Start a new module →
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
