import type { Run } from "@alpha/contracts";
import { ArrowRight, Boxes, Sparkles, type LucideIcon } from "lucide-react";
import type { AppSummary } from "../core/client";
import { Badge } from "../ui/Badge";
import "./pages.css";

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
  loading = false,
  error = null,
}: {
  modules: AppSummary[];
  icons: Record<string, LucideIcon>;
  runs: Run[];
  onOpen: (appId: string) => void;
  onNew: () => void;
  onActivity: () => void;
  /** Optional: a caller with a distinct "still loading the module list" moment can pass this. */
  loading?: boolean;
  /** Optional: a caller that surfaces a module-list fetch failure can pass this. */
  error?: string | null;
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
    <section className="page page--home" aria-labelledby="home-heading">
      <div className="eyebrow">
        <Sparkles size={14} aria-hidden="true" />
        {today.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}
      </div>
      <h1 id="home-heading">{greeting()}</h1>
      <p className="subcopy">Open a module to work with its records, or describe a new one.</p>

      <div className="stat-row">
        <div className="card stat-card">
          <div className="stat-card__label">Modules</div>
          <div className="stat-card__value">{modules.length}</div>
          <div className="stat-card__sub">{modules.length ? "Ready to use on this Mac" : "Describe what you want to make the first one"}</div>
        </div>
        <div className="card stat-card">
          <div className="stat-card__label">Ran today</div>
          <div className="stat-card__value">{ranToday.length}</div>
          <div className="stat-card__sub">{ranToday.length ? `${ranToday.filter((r) => r.state === "succeeded").length} finished fine` : "Nothing has run yet today"}</div>
        </div>
        <div className="card stat-card">
          <div className="stat-card__label">Needs you</div>
          <div className="stat-card__value">{attention.length}</div>
          <div className="stat-card__sub">
            {attention.length ? (
              <button type="button" className="module-card__open" onClick={onActivity}>
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
            <button type="button" className="module-card__open" onClick={onActivity}>
              See all activity
            </button>
          </div>
        </div>

        {error ? (
          <p className="home-state home-state--error" role="alert">
            Modules could not be loaded: {error}
          </p>
        ) : loading ? (
          <p className="home-state">Loading modules…</p>
        ) : (
          <div className="module-grid">
            {modules.map((m) => {
              const last = lastRunByApp.get(m.app_id);
              const Icon = icons[m.app_id] ?? Boxes;
              return (
                <div className="card module-card" key={m.app_id}>
                  <div className="module-card__top">
                    <div className="module-card__icon" aria-hidden="true">
                      <Icon size={18} strokeWidth={1.75} />
                    </div>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <h2>{m.name}</h2>
                      <div className="faint">{m.has_ui ? "Has its own screen" : `${m.actions} action${m.actions === 1 ? "" : "s"}`}</div>
                    </div>
                    <Badge variant={m.state === "active" ? "success" : "neutral"}>{m.state === "active" ? "Active" : m.state}</Badge>
                  </div>
                  <p>{m.description}</p>
                  <div className="module-card__meta">
                    <span>{last ? `Last ran ${ago(last.created_at)}` : `Made ${ago(m.created_at)}`}</span>
                    <button type="button" className="module-card__open" aria-label={`Open ${m.name}`} onClick={() => onOpen(m.app_id)}>
                      Open module <ArrowRight size={13} />
                    </button>
                  </div>
                </div>
              );
            })}
            <div className="card module-card module-card--new">
              <div className="eyebrow">New</div>
              <h2>Describe what you want</h2>
              <p>
                “Track what I eat”, “Watch a page for price drops”, “Turn my receipts into a monthly summary”. Alpha asks a couple of questions,
                then builds it here.
              </p>
              <button type="button" className="module-card__open" onClick={onNew}>
                Start a new module <ArrowRight size={13} />
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
