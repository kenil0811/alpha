/** Settings -> Models: whether Alpha can reach Claude through the Claude Code login on this Mac,
 *  said plainly, with the fix and the buttons to apply it. */
import { useCallback, useEffect, useState } from "react";
import type { CoreClient, ModelConnection } from "../core/client";

export type Tone = "good" | "warn" | "bad" | "gray";

const ERROR_WORDS: Record<string, string> = {
  timeout: "the model took too long to answer",
  cli_not_logged_in: "Claude Code is signed out",
  cli_too_old: "Claude Code is too old for Alpha",
  cli_missing: "Claude Code is not installed",
  cli_no_output: "Claude Code stopped without an answer",
  cli_bad_json: "Claude Code's answer could not be read",
};

/** The one-line status and the fix, for Settings, the assistant panel and the avatar. */
export function connectionSummary(c: ModelConnection): { tone: Tone; headline: string; fix: string | null } {
  switch (c.status) {
    case "connected":
      return { tone: "good", headline: "Connected", fix: null };
    case "signed_out":
      return { tone: "bad", headline: "Signed out of Claude Code", fix: c.fix };
    case "cli_missing":
      return { tone: "bad", headline: "Claude Code is not installed on this Mac", fix: c.fix };
    case "cli_too_old":
      return {
        tone: "bad",
        headline: `Claude Code ${c.cli_version ?? ""} is too old (Alpha needs ${c.min_supported_version} or newer)`.replace("  ", " "),
        fix: c.fix,
      };
    case "last_call_failed": {
      const e = c.last_error;
      const reason = e ? ERROR_WORDS[e.code] ?? e.message : "unknown reason";
      return { tone: "warn", headline: `Last call failed: ${reason}`, fix: c.fix };
    }
    default:
      return { tone: "gray", headline: "Not used on this copy of Alpha (it runs on its test model)", fix: null };
  }
}

/** Alpha cannot reach Claude at all until the person fixes something. */
export function isDisconnected(c: ModelConnection | null): boolean {
  return c !== null && (c.status === "signed_out" || c.status === "cli_missing" || c.status === "cli_too_old");
}

/** The connection as Core last reported it: asked on mount and every `intervalMs` while the
 *  window is visible; `refresh` asks now. Null until the first answer (or when unsupported). */
export function useModelConnection(client: CoreClient | null, intervalMs = 60_000) {
  const [connection, setConnection] = useState<ModelConnection | null>(null);
  const refresh = useCallback(() => {
    if (!client?.modelConnection) return;
    client
      .modelConnection()
      .then(setConnection)
      .catch(() => undefined); // a missed poll says nothing about the connection
  }, [client]);
  useEffect(() => {
    refresh();
    const timer = window.setInterval(() => {
      if (!document.hidden) refresh();
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [refresh, intervalMs]);
  return { connection, refresh, update: setConnection };
}

function ago(iso: string): string {
  const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
}

const LOGIN_WORDS: Record<NonNullable<ModelConnection["login"]>["state"], string> = {
  waiting: "A browser window has opened. Sign in there; this updates by itself.",
  signed_in: "Signed in.",
  timed_out: "Sign-in was not finished within five minutes. Press Sign in to try again.",
  not_completed: "Sign-in was not finished. Press Sign in to try again.",
};

export function ModelConnectionCard({
  client,
  connection,
  onRefresh,
  onUpdate,
}: {
  client: CoreClient;
  connection: ModelConnection | null;
  onRefresh: () => void;
  onUpdate: (next: ModelConnection) => void;
}) {
  const [busy, setBusy] = useState<"check" | "login" | null>(null);
  const [note, setNote] = useState<string | null>(null);
  // Fresh on open; while a sign-in is running, every two seconds until it ends.
  useEffect(onRefresh, [onRefresh]);
  const waiting = connection?.login?.state === "waiting";
  useEffect(() => {
    if (!waiting) return;
    const timer = window.setInterval(onRefresh, 2000);
    return () => window.clearInterval(timer);
  }, [waiting, onRefresh]);
  if (!client.modelConnection) return null;

  async function act(kind: "check" | "login") {
    setBusy(kind);
    setNote(null);
    try {
      const next = kind === "check" ? await client.checkModelConnection!() : await client.signInToClaude!();
      onUpdate(next);
      if (next.check) setNote(next.check.ok ? `A small call worked (${((next.check.elapsed_ms ?? 0) / 1000).toFixed(1)} s).` : `A small call failed: ${ERROR_WORDS[next.check.code ?? ""] ?? next.check.error ?? "unknown reason"}.`);
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const summary = connection ? connectionSummary(connection) : null;
  const account = connection?.account;
  return (
    <div className="card list" aria-label="Connection to Claude" id="settings-models">
      <div className="item">
        <div className="item__body">
          <b>Connection to Claude</b>
          <div className="item__sub">Alpha uses the Claude Code app on this Mac and your own Claude sign-in. Nothing is stored by Alpha.</div>
        </div>
        {summary ? <span className={`pill pill--${summary.tone === "gray" ? "gray" : summary.tone}`}>{summary.tone === "good" ? "Connected" : summary.tone === "gray" ? "Not used" : "Needs attention"}</span> : <span className="faint">Checking…</span>}
      </div>
      {connection && summary ? (
        <>
          <div className="item">
            <div className="item__body">
              <b role="status">{summary.headline}</b>
              {summary.fix ? <div className="item__sub">{renderFix(summary.fix)}</div> : null}
              {connection.login ? <div className="item__sub">{LOGIN_WORDS[connection.login.state]}</div> : null}
            </div>
            <span className="row" style={{ gap: 6 }}>
              {connection.status === "signed_out" || waiting ? (
                <button type="button" className="btn btn--primary btn--sm" disabled={busy !== null || waiting} onClick={() => void act("login")}>
                  {waiting ? "Waiting for sign-in…" : "Sign in"}
                </button>
              ) : null}
              <button type="button" className="btn btn--sm" disabled={busy !== null || !connection.route_enabled} onClick={() => void act("check")}>
                {busy === "check" ? "Checking…" : "Check now"}
              </button>
            </span>
          </div>
          <div className="item">
            <div className="item__body">
              <dl className="kv">
                <div className="kv__row">
                  <dt>Claude Code</dt>
                  <dd>{connection.cli_found ? `${connection.cli_version ?? "unknown version"}${connection.version_supported ? "" : ` (needs ${connection.min_supported_version})`}` : "Not found"}</dd>
                </div>
                <div className="kv__row">
                  <dt>Signed in as</dt>
                  <dd>{account ? [account.email, account.plan ? `${account.plan} plan` : null].filter(Boolean).join(" · ") : connection.logged_in === false ? "Signed out" : "Unknown"}</dd>
                </div>
                <div className="kv__row">
                  <dt>Last successful call</dt>
                  <dd>{connection.last_successful_call_at ? `${ago(connection.last_successful_call_at)}${connection.last_call_latency_ms != null ? ` · took ${(connection.last_call_latency_ms / 1000).toFixed(1)} s` : ""}` : "None yet"}</dd>
                </div>
                <div className="kv__row">
                  <dt>Checked</dt>
                  <dd>{ago(connection.checked_at)}</dd>
                </div>
              </dl>
            </div>
          </div>
        </>
      ) : null}
      {note ? (
        <p className="panel__hint" role="status" style={{ padding: "0 14px 10px" }}>
          {note}
        </p>
      ) : null}
    </div>
  );
}

/** `code` spans in a fix sentence ("run `claude update`"). */
function renderFix(text: string) {
  return text.split(/(`[^`]+`)/).map((part, i) => (part.startsWith("`") ? <code key={i}>{part.slice(1, -1)}</code> : <span key={i}>{part}</span>));
}

/** In the assistant panel: a failed turn that is really a connection problem says so. */
export function ConnectionProblem({ connection, onOpenSettings }: { connection: ModelConnection; onOpenSettings?: () => void }) {
  const summary = connectionSummary(connection);
  return (
    <div className="failure" role="alert" aria-label="Alpha cannot reach Claude">
      <p className="notice">Alpha could not reach Claude: {summary.headline}.</p>
      {summary.fix ? <p className="panel__hint">{renderFix(summary.fix)}</p> : null}
      {onOpenSettings ? (
        <button type="button" className="btn btn--sm" onClick={onOpenSettings}>
          Open Settings → Models
        </button>
      ) : null}
    </div>
  );
}
