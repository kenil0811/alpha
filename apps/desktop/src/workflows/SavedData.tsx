/** What an App has saved, per collection, newest first: the person's own records. */
import { useEffect, useState } from "react";
import type { CollectionSummary, RecordRow, WorkflowsClient } from "../core/client";
import { humanize } from "./schemaForm";

export function SavedData({
  client,
  appId,
  collections,
  refresh,
}: {
  client: WorkflowsClient;
  appId: string;
  collections: CollectionSummary[];
  refresh: number;
}) {
  if (!collections.length) return null;
  return (
    <section aria-labelledby="saved-heading" className="saved">
      <h3 id="saved-heading">Saved</h3>
      {collections.map((collection) => (
        <CollectionTable key={collection.name} client={client} appId={appId} collection={collection} refresh={refresh} />
      ))}
    </section>
  );
}

function CollectionTable({
  client,
  appId,
  collection,
  refresh,
}: {
  client: WorkflowsClient;
  appId: string;
  collection: CollectionSummary;
  refresh: number;
}) {
  const [rows, setRows] = useState<RecordRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    client
      .queryRecords(appId, collection.name, 25)
      .then((r) => {
        setRows(r);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [client, appId, collection.name, refresh]);
  const fields = collection.fields.slice(0, 5);
  const caption = humanize(collection.name);
  if (error) return <p className="notice" role="alert">{caption} could not be loaded: {error}</p>;
  if (rows === null) return <p className="panel__hint" role="status">Loading {caption.toLowerCase()}…</p>;
  if (!rows.length) return <p className="panel__hint">No {caption.toLowerCase()} saved yet.</p>;
  return (
    <div className="table-wrap">
      <table className="data">
        <caption>{caption}</caption>
        <thead>
          <tr>
            {fields.map((f) => (
              <th key={f.name} scope="col">
                {humanize(f.name)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              {fields.map((f) => (
                <td key={f.name}>
                  {row.values[f.name] === null || row.values[f.name] === undefined ? "—" : String(row.values[f.name])}
                  {row.provenance?.[f.name]?.source === "model_estimate" ? <span className="estimate"> (estimate)</span> : null}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
