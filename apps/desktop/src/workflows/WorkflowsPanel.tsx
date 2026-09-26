/** My workflows: the reusable Apps a person made, opened into their working surface. */
import { useEffect, useState } from "react";
import { CREATION_DONE, type AppSummary, type Creation, type WorkflowsClient } from "../core/client";

export function WorkflowsPanel({
  client,
  onOpen,
  onViewRequest,
}: {
  client: WorkflowsClient;
  onOpen: (appId: string) => void;
  onViewRequest?: (conversationId: string) => void;
}) {
  const [apps, setApps] = useState<AppSummary[] | null>(null);
  const [making, setMaking] = useState<Creation[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client
      .listApps()
      .then(setApps)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
    client
      .recentCreations()
      .then((all) => setMaking(all.filter((c) => !CREATION_DONE.has(c.state))))
      .catch(() => undefined);
  }, [client]);

  const created = (apps ?? []).filter((a) => a.origin !== "fixture");
  const fixtures = (apps ?? []).filter((a) => a.origin === "fixture");

  return (
    <section className="panel surface surface--reading" aria-labelledby="workflows-heading">
      <h2 id="workflows-heading">My workflows</h2>
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
      {apps === null && !error ? <p className="panel__hint" role="status">Loading…</p> : null}
      {making.length ? (
        <section aria-labelledby="making-heading" className="making">
          <h3 id="making-heading" className="workflow__name">Being made</h3>
          <ul className="workflows">
            {making.map((c) => (
              <li key={c.creation_id} className="workflow">
                <div>
                  <p className="workflow__name">{c.app_name ?? "A new workflow"}</p>
                  <p className="panel__hint">{c.label}</p>
                </div>
                {onViewRequest ? (
                  <button type="button" className="button" onClick={() => onViewRequest(c.conversation_id)}>
                    View progress
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {apps !== null && created.length === 0 && !making.length ? (
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
