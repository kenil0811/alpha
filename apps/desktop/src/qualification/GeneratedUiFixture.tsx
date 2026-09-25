/**
 * Qualification surface for F03: two "generated UI" sessions rendered in sandboxed,
 * opaque-origin frames, each bound to its own BridgeHost, grant and MessagePort.
 * Session A may invoke the synthetic action; session B may not. The frames can only reach
 * Core through the shell's handlers, which act with the shell's own credential.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { BridgeError, BridgeHost, type BridgeHostEvent, type BridgeSession } from "@alpha/ui-bridge";
import type { CoreClient } from "../core/client";
import { hasTauri } from "../core/session";
import fixtureHtml from "./generated-ui.html?raw";

/** Own origin per App inside Tauri (macOS/Linux form of a custom scheme); the srcdoc fallback
 *  exists for browser-only development and tests and inherits the shell CSP, which is exactly
 *  why it is not the product path. */
function fixtureSrc(appId: string, reload: number): string | null {
  return hasTauri() ? `alpha-ui://${appId}/index.html?r=${reload}` : null;
}

const SANDBOX = "allow-scripts";

interface FrameState {
  label: string;
  session: BridgeSession | null;
  events: string[];
  reloads: number;
}

function makeSession(appId: string, actions: string[]): BridgeSession {
  return {
    session_id: `sess_${Math.random().toString(36).slice(2, 12)}`,
    owner: { kind: "app", app_id: appId, release_id: "rel_fixture" },
    grant: { actions, read_views: [] },
    expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
  };
}

export function GeneratedUiFixture({ client }: { client: CoreClient }) {
  return (
    <section className="panel" aria-labelledby="fixture-heading">
      <h2 id="fixture-heading">Generated UI isolation fixture (qualification)</h2>
      <p className="panel__hint">
        Two sandboxed frames of arbitrary React. Session A may invoke <code>synthetic.echo</code>; session B may not.
        Frames hold one message port each and nothing else.
      </p>
      <div className="fixture__frames">
        <FixtureFrame label="A" appId="fixture_a" actions={["synthetic.echo"]} client={client} />
        <FixtureFrame label="B" appId="fixture_b" actions={[]} client={client} />
      </div>
    </section>
  );
}

function FixtureFrame({ label, appId, actions, client }: { label: string; appId: string; actions: string[]; client: CoreClient }) {
  const iframe = useRef<HTMLIFrameElement>(null);
  const host = useRef<BridgeHost | null>(null);
  const [state, setState] = useState<FrameState>({ label, session: null, events: [], reloads: 0 });
  const push = useCallback((line: string) => setState((s) => ({ ...s, events: [line, ...s.events].slice(0, 10) })), []);

  const establish = useCallback(() => {
    const frame = iframe.current;
    if (!frame?.contentWindow) return;
    host.current?.revoke("navigation");
    const session = makeSession(appId, actions);
    const onEvent = (event: BridgeHostEvent) => push(`${event.kind} ${JSON.stringify(event.detail)}`);
    const created = new BridgeHost({
      session,
      onEvent,
      handlers: {
        actionInvoke: async (_session, payload) => {
          if (payload.action_id !== "synthetic.echo") throw new BridgeError("not_found", "unknown action");
          const text = typeof payload.input.text === "string" ? payload.input.text : "";
          const run = await client.createRun({ text, mode: "succeed" });
          return { operation_id: run.run_id };
        },
        operationObserve: async (_session, payload) => {
          const run = await client.run(payload.operation_id);
          return { operation_id: run.run_id, state: run.state, output: run.output, latest_sequence: run.latest_sequence };
        },
      },
    });
    host.current = created;
    created.attachToWindow(frame.contentWindow);
    setState((s) => ({ ...s, session, events: [] }));
  }, [actions, appId, client, push]);

  useEffect(() => () => host.current?.revoke("unmounted"), []);

  // Attach only when the frame's own script says it is listening, and only for messages whose
  // source is exactly this frame's window (never by origin string: the origin is opaque).
  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const frame = iframe.current;
      if (!frame?.contentWindow || event.source !== frame.contentWindow) return;
      const data: unknown = event.data;
      if (typeof data !== "object" || data === null) return;
      const message = data as { type?: unknown; protocol_version?: unknown };
      if (message.type === "bridge.hello" && message.protocol_version === "0.2") establish();
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [establish]);

  return (
    <div className="fixture">
      <div className="row">
        <strong>Session {label}</strong>
        <span className="run__id">{state.session?.session_id ?? "—"}</span>
        <button type="button" className="button" onClick={() => host.current?.revoke("revoked by shell")}>Revoke</button>
        <button
          type="button"
          className="button"
          onClick={() => {
            setState((s) => ({ ...s, reloads: s.reloads + 1 }));
            const frame = iframe.current;
            if (!frame) return;
            const next = fixtureSrc(appId, state.reloads + 1);
            if (next) frame.src = next;
            else frame.srcdoc = fixtureHtml + `<!-- reload ${state.reloads + 1} -->`;
          }}
        >
          Reload frame
        </button>
      </div>
      <iframe
        ref={iframe}
        title={`Generated UI fixture ${label}`}
        sandbox={SANDBOX}
        src={fixtureSrc(appId, 0) ?? undefined}
        srcDoc={fixtureSrc(appId, 0) ? undefined : fixtureHtml}
        className="fixture__frame"
      />
      <ol className="fixture__events">
        {state.events.map((e, i) => (
          <li key={i}>{e}</li>
        ))}
      </ol>
    </div>
  );
}
