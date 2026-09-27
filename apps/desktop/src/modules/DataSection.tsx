/**
 * The Data section of a module: every table it keeps, as a spreadsheet the person can read,
 * correct, add to and prune. Edits go straight to Core as the person's own decision (kept
 * distinct from what the module wrote), never through the module's code.
 */
import { useCallback, useEffect, useMemo, useState, type FormEvent, type KeyboardEvent } from "react";
import type { AppDetail, CollectionSummary, RecordRow } from "../core/client";
import { formatDay, formatNumber, humanize, type ModuleClient } from "./useModule";

type Field = CollectionSummary["fields"][number];

function show(value: unknown, kind: string): string {
  if (value === null || value === undefined || value === "") return "";
  if (kind === "date") return formatDay(String(value));
  if (kind === "datetime") return new Date(String(value)).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  if (kind === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return formatNumber(value);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function coerce(text: string, kind: string): unknown {
  const trimmed = text.trim();
  if (trimmed === "") return null;
  if (kind === "number") return Number.isFinite(Number(trimmed)) ? Number(trimmed) : trimmed;
  if (kind === "integer") return Number.isInteger(Number(trimmed)) ? Number(trimmed) : trimmed;
  if (kind === "boolean") return trimmed === "true" || trimmed === "yes";
  if (kind === "json") {
    try {
      return JSON.parse(trimmed);
    } catch {
      return trimmed;
    }
  }
  return trimmed;
}

function inputType(kind: string): string {
  if (kind === "number" || kind === "integer") return "number";
  if (kind === "date") return "date";
  if (kind === "datetime") return "datetime-local";
  return "text";
}

export function DataSection({ client, detail, version, onChanged }: { client: ModuleClient; detail: AppDetail; version: number; onChanged: () => void }) {
  if (!detail.collections.length) return <p className="empty">This module keeps no tables.</p>;
  return (
    <div className="stack">
      {detail.collections.map((collection) => (
        <CollectionEditor key={collection.name} client={client} appId={detail.app_id} collection={collection} count={detail.record_counts[collection.name] ?? 0} version={version} onChanged={onChanged} />
      ))}
    </div>
  );
}

const PAGE = 50;

function CollectionEditor({ client, appId, collection, count, version, onChanged }: { client: ModuleClient; appId: string; collection: CollectionSummary; count: number; version: number; onChanged: () => void }) {
  const [rows, setRows] = useState<RecordRow[] | null>(null);
  const [next, setNext] = useState<string | null>(null);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const fields = collection.fields;
  const kinds = useMemo(() => new Map(fields.map((f) => [f.name, f])), [fields]);

  const load = useCallback(() => {
    if (!client.queryRecordsPage) return;
    client
      .queryRecordsPage(appId, { collection: collection.name, limit: PAGE, cursor: cursors[cursors.length - 1], order_by: [{ field: "created_at", direction: "desc" }] })
      .then((page) => {
        setRows(page.records);
        setNext(page.next_cursor);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [client, appId, collection.name, cursors]);
  useEffect(load, [load, version]);

  async function mutate(mutation: Record<string, unknown>, words: string) {
    if (!client.mutateRecord) return;
    setBusy(true);
    setError(null);
    try {
      await client.mutateRecord(appId, mutation);
      load();
      onChanged();
    } catch (e) {
      setError(`${words}: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  function commit(row: RecordRow, field: Field, text: string) {
    const value = coerce(text, field.kind);
    if (value === (row.values[field.name] ?? null)) return;
    void mutate({ op: "correct", collection: collection.name, id: row.id, expected_revision: row.revision, changes: { [field.name]: value } }, "Could not save the change");
  }

  function remove(row: RecordRow) {
    void mutate({ op: "delete", collection: collection.name, id: row.id, expected_revision: row.revision }, "Could not remove it");
  }

  async function add(event: FormEvent) {
    event.preventDefault();
    const values: Record<string, unknown> = {};
    for (const field of fields) {
      const text = draft[field.name] ?? "";
      if (field.kind === "boolean") values[field.name] = text === "true";
      else if (text.trim() !== "") values[field.name] = coerce(text, field.kind);
    }
    await mutate({ op: "create", collection: collection.name, values }, "Could not add it");
    setDraft({});
    setAdding(false);
  }

  return (
    <div className="card">
      <div className="toolbar">
        <b>{humanize(collection.name)}</b>
        <span className="faint">
          {count} record{count === 1 ? "" : "s"}
          {collection.description ? ` · ${collection.description}` : ""}
        </span>
        <span className="toolbar__hint">Click a cell to edit</span>
        <button type="button" className="btn btn--sm" onClick={() => setAdding((a) => !a)} aria-expanded={adding}>
          {adding ? "Cancel" : "Add a row"}
        </button>
      </div>
      {adding ? (
        <form className="action" style={{ border: 0, borderRadius: 0, borderBottom: "1px solid var(--border)" }} onSubmit={add} aria-label={`Add to ${humanize(collection.name)}`}>
          {fields.map((f) => (
            <div key={f.name} className="field">
              <label htmlFor={`add-${collection.name}-${f.name}`}>
                {humanize(f.name)}
                {f.required ? "" : " (optional)"}
              </label>
              {f.kind === "choice" ? (
                <select id={`add-${collection.name}-${f.name}`} value={draft[f.name] ?? ""} onChange={(e) => setDraft((d) => ({ ...d, [f.name]: e.target.value }))}>
                  <option value="">Choose…</option>
                  {(f.choices ?? []).map((c) => (
                    <option key={c} value={c}>
                      {humanize(c)}
                    </option>
                  ))}
                </select>
              ) : f.kind === "boolean" ? (
                <select id={`add-${collection.name}-${f.name}`} value={draft[f.name] ?? "false"} onChange={(e) => setDraft((d) => ({ ...d, [f.name]: e.target.value }))}>
                  <option value="false">No</option>
                  <option value="true">Yes</option>
                </select>
              ) : (
                <input id={`add-${collection.name}-${f.name}`} type={inputType(f.kind)} step={f.kind === "number" ? "any" : undefined} value={draft[f.name] ?? ""} onChange={(e) => setDraft((d) => ({ ...d, [f.name]: e.target.value }))} />
              )}
            </div>
          ))}
          <div className="row">
            <button type="submit" className="btn btn--primary btn--sm" disabled={busy}>
              Add
            </button>
          </div>
        </form>
      ) : null}
      {error ? (
        <p className="notice" style={{ padding: "8px 12px" }} role="alert">
          {error}
        </p>
      ) : null}
      <div className="tablewrap">
        <table className="table" aria-label={humanize(collection.name)}>
          <thead>
            <tr>
              {fields.map((f) => (
                <th key={f.name} className={f.kind === "number" || f.kind === "integer" ? "r" : undefined}>
                  {humanize(f.name)}
                </th>
              ))}
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {(rows ?? []).map((row) => (
              <tr key={row.id}>
                {fields.map((f) => (
                  <EditableCell key={f.name} row={row} field={f} kind={kinds.get(f.name)?.kind ?? "text"} onCommit={(text) => commit(row, f, text)} />
                ))}
                <td className="r">
                  <button type="button" className="btn btn--sm btn--ghost rowbtn" aria-label={`Remove ${row.id}`} title="Remove" onClick={() => remove(row)}>
                    ✕
                  </button>
                </td>
              </tr>
            ))}
            {rows && !rows.length ? (
              <tr>
                <td colSpan={fields.length + 1} className="empty" style={{ whiteSpace: "normal" }}>
                  Nothing here yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      {(cursors.length > 1 || next) && (
        <div className="pager">
          <span>{rows ? `${rows.length} shown` : "Loading…"}</span>
          <span className="spacer" />
          <button type="button" className="btn btn--sm" disabled={cursors.length <= 1} onClick={() => setCursors((c) => c.slice(0, -1))}>
            Previous
          </button>
          <button type="button" className="btn btn--sm" disabled={!next} onClick={() => setCursors((c) => [...c, next])}>
            Next
          </button>
        </div>
      )}
    </div>
  );
}

function EditableCell({ row, field, kind, onCommit }: { row: RecordRow; field: Field; kind: string; onCommit: (text: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const value = row.values[field.name];
  const numeric = kind === "number" || kind === "integer";
  const corrected = row.provenance?.[field.name]?.source === "user_correction";
  const estimate = row.provenance?.[field.name]?.source === "model_estimate";
  function begin() {
    setText(value === null || value === undefined ? "" : typeof value === "object" ? JSON.stringify(value) : String(value));
    setEditing(true);
  }
  function finish(commit: boolean) {
    setEditing(false);
    if (commit) onCommit(text);
  }
  function key(e: KeyboardEvent) {
    if (e.key === "Enter") finish(true);
    if (e.key === "Escape") finish(false);
  }
  if (editing) {
    return (
      <td className={numeric ? "r" : undefined}>
        {kind === "choice" ? (
          <select autoFocus value={text} onChange={(e) => setText(e.target.value)} onBlur={() => finish(true)} onKeyDown={key} aria-label={humanize(field.name)}>
            <option value="">—</option>
            {(field.choices ?? []).map((c) => (
              <option key={c} value={c}>
                {humanize(c)}
              </option>
            ))}
          </select>
        ) : kind === "boolean" ? (
          <select autoFocus value={text === "true" ? "true" : "false"} onChange={(e) => setText(e.target.value)} onBlur={() => finish(true)} onKeyDown={key} aria-label={humanize(field.name)}>
            <option value="false">No</option>
            <option value="true">Yes</option>
          </select>
        ) : (
          <input autoFocus type={inputType(kind)} step={kind === "number" ? "any" : undefined} value={text} onChange={(e) => setText(e.target.value)} onFocus={(e) => e.currentTarget.select()} onBlur={() => finish(true)} onKeyDown={key} aria-label={humanize(field.name)} />
        )}
      </td>
    );
  }
  return (
    <td className={`${numeric ? "r num" : ""} editable`.trim()} onClick={begin} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && begin()} title={corrected ? "You changed this" : estimate ? "A model estimate" : "Click to edit"}>
      {show(value, kind) || <span className="faint">—</span>}
      {estimate ? <span className="est">estimate</span> : null}
    </td>
  );
}
