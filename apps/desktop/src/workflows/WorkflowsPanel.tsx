/** My workflows: the reusable Apps a person made, opened into their working surface. */
import { useEffect, useState } from "react";
import type { AppSummary, WorkflowsClient } from "../core/client";

export function WorkflowsPanel({ client, onOpen }: { client: WorkflowsClient; onOpen: (appId: string) => void }) {
  const [apps, setApps] = useState<AppSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client
      .listApps()
      .then(setApps)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [client]);

  const created = (apps ?? []).filter((a) => a.origin !== "fixture");
  const fixtures = (apps ?? []).filter((a) => a.origin === "fixture");

  return (
    <section className="panel panel--wide" aria-labelledby="workflows-heading">
      <h2 id="workflows-heading">My workflows</h2>
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
      {apps === null && !error ? <p className="panel__hint" role="status">Loading…</p> : null}
      {apps !== null && created.length === 0 ? (
        <div className="empty">
          <p>Nothing here yet.</p>
          <p className="panel__hint">Ask the Assistant for something you want to keep using, like a tracker or a review list.</p>
        </div>
      ) : null}
      <ul className="workflows">
        {created.map((app) => (
          <WorkflowTile key={app.app_id} app={app} onOpen={onOpen} />
        ))}
      </ul>
      {fixtures.length ? (
        <details>
          <summary>Development fixtures ({fixtures.length})</summary>
          <ul className="workflows">
            {fixtures.map((app) => (
              <WorkflowTile key={app.app_id} app={app} onOpen={onOpen} />
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

function WorkflowTile({ app, onOpen }: { app: AppSummary; onOpen: (appId: string) => void }) {
  return (
    <li className="workflow">
      <div>
        <h3 className="workflow__name">{app.name}</h3>
        <p className="panel__hint">{app.description}</p>
        <p className="workflow__meta">
          {app.has_ui ? "Has its own screen" : `${app.actions} action${app.actions === 1 ? "" : "s"}, run from Alpha`}
          {app.state !== "active" ? ` · ${app.state}` : ""}
        </p>
      </div>
      <button type="button" className="button button--primary" onClick={() => onOpen(app.app_id)} aria-label={`Open ${app.name}`}>
        Open
      </button>
    </li>
  );
}
