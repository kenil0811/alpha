/**
 * F06 qualification surface: the two neutral kit compositions, each in its own sandboxed,
 * opaque-origin frame with its own bridge session, backed by a real installed App (the neutral
 * entries fixture) through Core. Reads go through Core-enforced views; changes through the App's
 * UI-callable actions, run in the App's worker. Nothing here is a product screen.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { BridgeHost, type BridgeHostEvent } from "@alpha/ui-bridge";
import { appBridgeHandlers, appSession } from "../apps/appBridge";
import { CoreError, type AppDetail, type AppsClient } from "../core/client";

const APP_ID = "entries-fixture";
// Built by scripts/build-compositions.mjs into public/. Each is framed with sandbox="allow-scripts"
// (opaque origin, the document's own hash-pinned CSP). The harness page has no CSP of its own, so
// the document is passed as srcdoc: nothing is fetched by the sandboxed frame.
const COMPOSITIONS = [
  { id: "review", title: "Composition A: review, filter, correct" },
  { id: "entry", title: "Composition B: quick entry and trend" },
] as const;

type Status = { kind: "loading" } | { kind: "missing"; message: string } | { kind: "ready"; detail: AppDetail } | { kind: "failed"; message: string };

export function KitFixture({ client }: { client: AppsClient }) {
  const [status, setStatus] = useState<Status>({ kind: "loading" });
  const load = useCallback(() => {
    setStatus({ kind: "loading" });
    client
      .appDetail(APP_ID)
      .then((detail) => setStatus({ kind: "ready", detail }))
      .catch((error: unknown) => {
        if (error instanceof CoreError && error.status === 404) {
          setStatus({ kind: "missing", message: "The neutral entries fixture App is not installed in this Core." });
        } else setStatus({ kind: "failed", message: error instanceof Error ? error.message : String(error) });
      });
  }, [client]);
  useEffect(load, [load]);

  return (
    <section className="panel panel--wide" aria-labelledby="kit-fixture-heading">
      <h2 id="kit-fixture-heading">UI kit fixture (qualification)</h2>
      <p className="panel__hint">
        Two neutral compositions built from the pinned kit, each in a sandboxed frame with its own bridge session to the{" "}
        <code>{APP_ID}</code> App through Core.
      </p>
      {status.kind === "loading" ? <p>Loading…</p> : null}
      {status.kind === "failed" ? <p role="alert">{status.message}</p> : null}
      {status.kind === "missing" ? (
        <div className="row">
          <span>{status.message}</span>
          <button
            type="button"
            className="button"
            onClick={() =>
              client
                .installFixtureApp("entries_app")
                .then(load)
                .catch((error: unknown) =>
                  setStatus({
                    kind: "missing",
                    message:
                      error instanceof CoreError && error.status === 404
                        ? "Fixture installs are disabled in this Core (start it with ALPHA_DEV_FIXTURE_APPS_DIR)."
                        : String(error),
                  }),
                )
            }
          >
            Install fixture App
          </button>
        </div>
      ) : null}
      {status.kind === "ready" ? (
        <div className="kit-fixture__frames">
          {COMPOSITIONS.map((composition) => (
            <CompositionFrame key={composition.id} client={client} detail={status.detail} {...composition} />
          ))}
        </div>
      ) : null}
    </section>
  );
}

function CompositionFrame({ client, detail, id, title }: { client: AppsClient; detail: AppDetail; id: string; title: string }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [html, setHtml] = useState<string | null>(null);
  useEffect(() => {
    void fetch(`/qualification/compositions/${id}.html`)
      .then((response) => response.text())
      .then(setHtml);
  }, [id]);
  const host = useRef<BridgeHost | null>(null);
  const [events, setEvents] = useState<string[]>([]);
  const [reloads, setReloads] = useState(0);

  const establish = useCallback(() => {
    const target = frame.current?.contentWindow;
    if (!target) return;
    host.current?.revoke("reloaded");
    const onEvent = (event: BridgeHostEvent) =>
      setEvents((list) => [`${event.kind} ${JSON.stringify(event.detail)}`, ...list].slice(0, 8));
    const created = new BridgeHost({ session: appSession(detail), handlers: appBridgeHandlers(client, detail.app_id), onEvent });
    host.current = created;
    created.attachToWindow(target);
  }, [client, detail]);

  useEffect(() => () => host.current?.revoke("unmounted"), []);
  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (!frame.current?.contentWindow || event.source !== frame.current.contentWindow) return;
      const data = event.data as { type?: unknown; protocol_version?: unknown } | null;
      if (data?.type === "bridge.hello" && data.protocol_version === "0.2") establish();
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [establish]);

  return (
    <div className="kit-fixture__frame-wrap" data-composition={id}>
      <div className="row">
        <strong>{title}</strong>
        <button type="button" className="button" onClick={() => setReloads((r) => r + 1)}>
          Reload
        </button>
        <button type="button" className="button" onClick={() => host.current?.revoke("revoked by shell")}>
          Revoke session
        </button>
      </div>
      {html ? (
        <iframe key={reloads} ref={frame} title={title} sandbox="allow-scripts" srcDoc={html} className="kit-fixture__frame" />
      ) : (
        <p>Loading the composition…</p>
      )}
      <details>
        <summary>Bridge events</summary>
        <ol className="fixture__events">
          {events.map((event, index) => (
            <li key={index}>{event}</li>
          ))}
        </ol>
      </details>
    </div>
  );
}
