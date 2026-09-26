import { useCallback, useEffect, useState } from "react";
import type { CoreClient, HealthInfo } from "./core/client";
import { HttpCoreClient, isAppsClient, isWorkflowsClient } from "./core/client";
import { WorkflowsPanel } from "./workflows/WorkflowsPanel";
import { Workspace } from "./workflows/Workspace";
import { resolveSession } from "./core/session";
import { RequestPanel } from "./components/RequestPanel";
import { RunList } from "./components/RunList";
import { useRuns } from "./components/useRuns";
import { GeneratedUiFixture } from "./qualification/GeneratedUiFixture";
import { AssistantPanel } from "./assistant/AssistantPanel";

type Surface = { kind: "assistant" } | { kind: "workflows" } | { kind: "workspace"; appId: string } | { kind: "activity" };

/** Development-only qualification fixtures: shown only in a development build opened with ?dev. */
function devTools(): boolean {
  return import.meta.env.DEV && typeof window !== "undefined" && new URLSearchParams(window.location.search).has("dev");
}

const SELECTED_KEY = "alpha.selectedConversation";

/** The conversation the Assistant shows, remembered in this window so reopening Alpha returns to
 *  it. Storage can be unavailable; then Alpha simply starts on a new request. */
function rememberedConversation(): string | null {
  try {
    return window.localStorage.getItem(SELECTED_KEY);
  } catch {
    return null;
  }
}

function remember(id: string | null): void {
  try {
    if (id) window.localStorage.setItem(SELECTED_KEY, id);
    else window.localStorage.removeItem(SELECTED_KEY);
  } catch {
    /* per-window convenience only */
  }
}

type Runtime =
  | { kind: "connecting" }
  | { kind: "connected"; client: CoreClient; health: HealthInfo }
  | { kind: "unavailable"; reason: string };

export function App({ client: injected, devTools: devOverride }: { client?: CoreClient; devTools?: boolean } = {}) {
  const [runtime, setRuntime] = useState<Runtime>({ kind: "connecting" });
  const [showFixture, setShowFixture] = useState(false);
  const [showRuntime, setShowRuntime] = useState(false);
  const [surface, setSurface] = useState<Surface>({ kind: "assistant" });
  const [conversationId, setConversationId] = useState<string | null>(rememberedConversation);
  const dev = devOverride ?? devTools();
  const selectConversation = useCallback((id: string | null) => {
    setConversationId(id);
    remember(id);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let client = injected;
      if (!client) {
        const resolution = await resolveSession();
        if (resolution.kind === "unavailable") {
          if (!cancelled) setRuntime({ kind: "unavailable", reason: resolution.reason });
          return;
        }
        client = new HttpCoreClient(resolution.session);
      }
      try {
        const health = await client.health();
        if (!cancelled) setRuntime({ kind: "connected", client, health });
      } catch (error) {
        if (!cancelled) setRuntime({ kind: "unavailable", reason: `Runtime not reachable: ${String(error)}` });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [injected]);

  return (
    <div className="frame">
      <header className="frame__header">
        <div>
          <h1 className="frame__title">Alpha</h1>
          <div className="frame__subtitle">
            Internal development build · runs while Alpha is running on this Mac · closing the window keeps it running
          </div>
        </div>
        {runtime.kind === "connected" ? (
          <nav className="nav" aria-label="Alpha">
            {(
              [
                ["assistant", "Assistant"],
                ["workflows", "My workflows"],
                ["activity", "Activity"],
              ] as const
            ).map(([kind, label]) => {
              const current = surface.kind === kind || (kind === "workflows" && surface.kind === "workspace");
              return (
                <button
                  key={kind}
                  type="button"
                  className={current ? "nav__item nav__item--current" : "nav__item"}
                  aria-current={current ? "page" : undefined}
                  onClick={() => setSurface({ kind })}
                >
                  {label}
                </button>
              );
            })}
          </nav>
        ) : null}
        <div className="row">
          {runtime.kind === "connected" && dev ? (
            <>
              <button type="button" className="button" onClick={() => setShowRuntime((v) => !v)}>
                {showRuntime ? "Hide runtime fixture" : "Runtime fixture"}
              </button>
              <button type="button" className="button" onClick={() => setShowFixture((v) => !v)}>
                {showFixture ? "Hide isolation fixture" : "Isolation fixture"}
              </button>
            </>
          ) : null}
          <RuntimeStatus runtime={runtime} />
        </div>
      </header>
      <main className={dev && (showFixture || showRuntime) ? "frame__main frame__main--three" : "frame__main"}>
        {runtime.kind === "connected" ? (
          <>
            {surface.kind === "assistant" ? (
              <AssistantPanel
                client={runtime.client}
                conversationId={conversationId}
                onSelect={selectConversation}
                onOpenApp={(appId) => setSurface({ kind: "workspace", appId })}
              />
            ) : null}
            {surface.kind === "workflows" && isWorkflowsClient(runtime.client) ? (
              <WorkflowsPanel
                client={runtime.client}
                onOpen={(appId) => setSurface({ kind: "workspace", appId })}
                onViewRequest={(id) => {
                  selectConversation(id);
                  setSurface({ kind: "assistant" });
                }}
              />
            ) : null}
            {surface.kind === "workspace" && isWorkflowsClient(runtime.client) && isAppsClient(runtime.client) ? (
              <Workspace client={runtime.client} appId={surface.appId} onBack={() => setSurface({ kind: "workflows" })} />
            ) : null}
            {surface.kind === "activity" || (dev && showRuntime) ? <Connected client={runtime.client} showRequest={dev && showRuntime} /> : null}
            {dev && showFixture ? <GeneratedUiFixture client={runtime.client} /> : null}
          </>
        ) : (
          <section className="panel">
            <h2>Runtime</h2>
            {runtime.kind === "connecting" ? (
              <p className="panel__hint">Connecting to the local runtime…</p>
            ) : (
              <p className="notice" role="alert">
                {runtime.reason}
              </p>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

function RuntimeStatus({ runtime }: { runtime: Runtime }) {
  const label =
    runtime.kind === "connected"
      ? `Runtime connected · Core ${runtime.health.core_version} · Python ${runtime.health.python_version.split(" ")[0]}`
      : runtime.kind === "connecting"
        ? "Connecting to runtime"
        : "Runtime unavailable";
  return (
    <span className={`status status--${runtime.kind}`} role="status">
      <span className="status__dot" aria-hidden="true" />
      {label}
    </span>
  );
}

function Connected({ client, showRequest }: { client: CoreClient; showRequest: boolean }) {
  const { runs, error, submit, cancel } = useRuns(client);
  return (
    <>
      {showRequest ? <RequestPanel onSubmit={submit} /> : null}
      <section className="panel" aria-labelledby="results-heading">
        <h2 id="results-heading">Activity</h2>
        {error ? (
          <p className="notice" role="alert">
            {error}
          </p>
        ) : null}
        <RunList runs={runs} onCancel={cancel} />
      </section>
    </>
  );
}
