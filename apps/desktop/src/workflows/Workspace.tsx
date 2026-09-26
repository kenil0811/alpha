/** A workflow's working surface: its own screen when it has one, otherwise Alpha's actions view,
 *  with what it has saved alongside. Trusted chrome stays outside the generated screen. */
import { useCallback, useEffect, useState } from "react";
import type { AppDetail, AppsClient, WorkflowsClient } from "../core/client";
import { ActionsView } from "./ActionsView";
import { GeneratedScreen } from "./GeneratedScreen";
import { SavedData } from "./SavedData";

export function Workspace({
  client,
  appId,
  onBack,
}: {
  client: WorkflowsClient & AppsClient;
  appId: string;
  onBack: () => void;
}) {
  const [detail, setDetail] = useState<AppDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const changed = useCallback(() => setRefresh((n) => n + 1), []);

  useEffect(() => {
    client
      .appDetail(appId)
      .then(setDetail)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [client, appId]);

  return (
    <section className={detail?.ui?.entry ? "panel surface workspace workspace--screen" : "panel surface workspace"} aria-labelledby="workspace-heading">
      <div className="workspace__head">
        <button type="button" className="button" onClick={onBack}>
          ← My workflows
        </button>
        <div>
          <h2 id="workspace-heading">{detail?.name ?? "Opening…"}</h2>
          {detail ? <p className="panel__hint">{detail.description}</p> : null}
        </div>
      </div>
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
      {detail ? (
        detail.ui?.entry ? (
          <>
            <GeneratedScreen client={client} detail={detail} />
            <details>
              <summary>Actions and saved data</summary>
              <ActionsView client={client} appId={appId} actions={detail.actions} onChanged={changed} />
              <SavedData client={client} appId={appId} collections={detail.collections} refresh={refresh} />
            </details>
          </>
        ) : (
          <>
            <ActionsView client={client} appId={appId} actions={detail.actions} onChanged={changed} />
            <SavedData client={client} appId={appId} collections={detail.collections} refresh={refresh} />
          </>
        )
      ) : null}
      {detail ? (
        <p className="workspace__meta" title={`Version ${detail.version_id} · runtime ${detail.runtime_profile_id}`}>
          {detail.data_notice ?? "Its records stay on this Mac."}
        </p>
      ) : null}
    </section>
  );
}
