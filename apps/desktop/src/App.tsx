import { useEffect, useState } from "react";
import type { CoreClient, HealthInfo } from "./core/client";
import { HttpCoreClient } from "./core/client";
import { resolveSession } from "./core/session";
import { RequestPanel } from "./components/RequestPanel";
import { RunList } from "./components/RunList";
import { useRuns } from "./components/useRuns";
import { GeneratedUiFixture } from "./qualification/GeneratedUiFixture";

type Runtime =
  | { kind: "connecting" }
  | { kind: "connected"; client: CoreClient; health: HealthInfo }
  | { kind: "unavailable"; reason: string };

export function App({ client: injected }: { client?: CoreClient } = {}) {
  const [runtime, setRuntime] = useState<Runtime>({ kind: "connecting" });
  const [showFixture, setShowFixture] = useState(false);

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
        <div className="row">
          {runtime.kind === "connected" ? (
            <button type="button" className="button" onClick={() => setShowFixture((v) => !v)}>
              {showFixture ? "Hide isolation fixture" : "Isolation fixture"}
            </button>
          ) : null}
          <RuntimeStatus runtime={runtime} />
        </div>
      </header>
      <main className={showFixture ? "frame__main frame__main--three" : "frame__main"}>
        {runtime.kind === "connected" ? (
          <>
            <Connected client={runtime.client} />
            {showFixture ? <GeneratedUiFixture client={runtime.client} /> : null}
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

function Connected({ client }: { client: CoreClient }) {
  const { runs, error, submit, cancel } = useRuns(client);
  return (
    <>
      <RequestPanel onSubmit={submit} />
      <section className="panel" aria-labelledby="results-heading">
        <h2 id="results-heading">Results</h2>
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
