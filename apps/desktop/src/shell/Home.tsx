import type { Run } from "@alpha/contracts";
import { type FormEvent, useEffect, useState } from "react";
import { type AppSummary, type Nudge, type OnboardingStatus, type ProfileClient } from "../core/client";

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

/** The first conversation, once: five short questions, then Alpha's proposed first shape. */
export function FirstSteps({ client, onStart }: { client: ProfileClient; onStart: (request: string) => void }) {
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    client
      .onboarding()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, [client]);
  if (!status || (status.done && !status.proposal?.options.length)) return null;
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setStatus(await client.answerOnboarding(answers));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }
  async function skip() {
    try {
      setStatus(await client.skipOnboarding());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }
  if (status.done && status.proposal) {
    return (
      <div className="card card--pad firststeps" aria-label="Where to begin">
        <div className="eyebrow">Where to begin</div>
        <p style={{ marginTop: 4 }}>{status.proposal.intro}</p>
        <div className="proposal__options">
          {status.proposal.options.map((o) => (
            <div key={o.title} className="proposal__option">
              <b>{o.title}</b>
              <p>{o.request}</p>
              <p className="faint">{o.why}</p>
              <button type="button" className="btn btn--sm btn--primary" onClick={() => onStart(o.request)}>
                Start with this
              </button>
            </div>
          ))}
        </div>
        <button type="button" className="btn btn--sm btn--ghost" onClick={() => void skip()}>
          Dismiss
        </button>
      </div>
    );
  }
  return (
    <form className="card card--pad firststeps" aria-label="First steps" onSubmit={submit}>
      <div className="eyebrow">First steps</div>
      <p style={{ marginTop: 4 }}>Five short answers and Alpha proposes where to begin. Everything you say lands on your About you page, where you can change it.</p>
      <div className="firststeps__grid">
        {status.questions.map((q) => (
          <div key={q.id} className="field field--compact">
            <label htmlFor={`first-${q.id}`}>{q.label}</label>
            <input id={`first-${q.id}`} value={answers[q.id] ?? ""} placeholder={q.hint} onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))} />
          </div>
        ))}
      </div>
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
      <div className="row">
        <button type="submit" className="btn btn--primary btn--sm" disabled={busy || !Object.values(answers).some((v) => v.trim())}>
          {busy ? "Thinking…" : "Propose where to begin"}
        </button>
        <button type="button" className="btn btn--sm btn--ghost" onClick={() => void skip()} disabled={busy}>
          Skip for now
        </button>
      </div>
    </form>
  );
}

/** What Alpha noticed in its weekly look: suggestions only, each a request away or dismissed. */
export function Noticed({ client, onStart }: { client: ProfileClient; onStart: (request: string) => void }) {
  const [rows, setRows] = useState<Nudge[]>([]);
  useEffect(() => {
    client
      .nudges()
      .then((r) => setRows(r.nudges))
      .catch(() => undefined);
  }, [client]);
  if (!rows.length) return null;
  return (
    <div className="card card--pad noticed" aria-label="Alpha noticed">
      <div className="eyebrow">Alpha noticed</div>
      <ul className="noticed__list">
        {rows.map((n) => (
          <li key={n.nudge_id}>
            <span>{n.text}</span>
            <span className="row" style={{ gap: 6 }}>
              <button type="button" className="btn btn--sm" onClick={() => onStart(n.next_step)}>
                {n.next_step}
              </button>
              <button type="button" className="btn btn--sm btn--ghost" aria-label="Dismiss" title="Dismiss" onClick={() => void client.dismissNudge(n.nudge_id).then(() => setRows((all) => all.filter((x) => x.nudge_id !== n.nudge_id)))}>
                ✕
              </button>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Home({
  modules,
  icons,
  runs,
  onOpen,
  onNew,
  onActivity,
  client,
  onStart,
}: {
  modules: AppSummary[];
  icons: Record<string, string>;
  runs: Run[];
  onOpen: (appId: string) => void;
  onNew: () => void;
  onActivity: () => void;
  client?: ProfileClient;
  onStart?: (request: string) => void;
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
      {client && onStart ? <FirstSteps client={client} onStart={onStart} /> : null}
      {client && onStart ? <Noticed client={client} onStart={onStart} /> : null}
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
            return (
              <div className="card modcard" key={m.app_id}>
                <div className="modcard__top">
                  <div className="modcard__ico" aria-hidden="true">
                    {icons[m.app_id] ?? "▦"}
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
