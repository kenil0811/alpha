/**
 * The shell-provided view for an App without its own screen: each action the person may run,
 * with a form from its declared inputs, and its result in plain words. Runs go through Core
 * like any other, and the result shown is only what the platform reports.
 */
import { useState, type FormEvent } from "react";
import type { ActionSummary, OperationOutcome, WorkflowsClient } from "../core/client";
import { InfoTip } from "../ui/InfoTip";
import { formFields, humanize, toInput, type FormValues } from "./schemaForm";

const DONE = new Set(["succeeded", "failed", "cancelled", "interrupted"]);

export async function runAndWait(
  client: WorkflowsClient,
  appId: string,
  action: ActionSummary,
  input: Record<string, unknown>,
  { pollMs = 400, timeoutMs = 300_000, onStarted }: { pollMs?: number; timeoutMs?: number; onStarted?: (runId: string) => void } = {},
): Promise<OperationOutcome> {
  const origin = action.invocable_from.includes("manual") ? "user" : "ui";
  const run = await client.runAppAction(appId, action.id, input, origin);
  onStarted?.(run.run_id);
  const deadline = Date.now() + timeoutMs;
  let outcome = await client.operationOutcome(run.run_id);
  while (!DONE.has(outcome.state) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, pollMs));
    outcome = await client.operationOutcome(run.run_id);
  }
  return outcome;
}

/** Actions a person can fill in: every input is a plain field (no structured data to paste). */
export function personActions(actions: ActionSummary[]): { usable: ActionSummary[]; internal: number } {
  const runnable = actions.filter((a) => a.invocable_from.includes("manual") || a.invocable_from.includes("ui"));
  const usable = runnable.filter((a) => formFields(a.input_schema).every((f) => f.kind !== "json"));
  return { usable, internal: runnable.length - usable.length };
}

export function ActionsView({
  client,
  appId,
  actions,
  primary = null,
  onChanged,
}: {
  client: WorkflowsClient;
  appId: string;
  actions: ActionSummary[];
  primary?: string | null;
  onChanged: () => void;
}) {
  const { usable, internal } = personActions(actions);
  if (!usable.length) return <p className="panel__hint">This App has nothing to run by hand.</p>;
  // The App's main action leads (M1 review finding F03); other simple actions stay reachable.
  const main = usable.find((a) => a.id === primary) ?? (usable.length === 1 ? usable[0] : null);
  const others = usable.filter((a) => a !== main);
  return (
    <div className="actions">
      {main ? <ActionForm client={client} appId={appId} action={main} onChanged={onChanged} primary /> : null}
      {main && others.length ? (
        <details className="actions__more">
          <summary>More actions ({others.length})</summary>
          {others.map((action) => (
            <ActionForm key={action.id} client={client} appId={appId} action={action} onChanged={onChanged} />
          ))}
        </details>
      ) : (
        others.map((action) => <ActionForm key={action.id} client={client} appId={appId} action={action} onChanged={onChanged} />)
      )}
      {internal ? (
        <p className="panel__hint">
          {internal === 1 ? "One more step runs" : `${internal} more steps run`} inside this workflow and needs no input from you.
        </p>
      ) : null}
    </div>
  );
}

export function ActionForm({
  client,
  appId,
  action,
  onChanged,
  primary = false,
  initial = {},
  title,
  description,
  submitLabel,
}: {
  client: WorkflowsClient;
  appId: string;
  action: ActionSummary;
  onChanged: () => void;
  primary?: boolean;
  /** Starting values, for settings-like actions that show what is currently set. */
  initial?: FormValues;
  title?: string;
  description?: string | null;
  submitLabel?: string;
}) {
  const fields = formFields(action.input_schema);
  // What the action assumes for fields left alone starts filled in, so the person sees it.
  const [values, setValues] = useState<FormValues>(() => {
    const seeded: FormValues = {};
    for (const field of fields) if (field.defaultValue !== null && field.kind !== "json") seeded[field.name] = field.defaultValue;
    return { ...seeded, ...initial };
  });
  const [state, setState] = useState<"idle" | "running" | "done" | "failed">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [output, setOutput] = useState<Record<string, unknown> | null>(null);
  const [runId, setRunId] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const { input, problems } = toInput(fields, values);
    if (problems.length) {
      setState("failed");
      setMessage(problems.join(" "));
      return;
    }
    setState("running");
    setMessage(null);
    setOutput(null);
    try {
      const outcome = await runAndWait(client, appId, action, input, { onStarted: setRunId });
      if (outcome.state === "succeeded") {
        setState("done");
        setOutput(outcome.output);
        onChanged();
      } else {
        setState("failed");
        setMessage(outcome.state === "cancelled" ? "You stopped it." : (outcome.error?.message ?? `It ${outcome.state}.`));
      }
    } catch (e) {
      setState("failed");
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setRunId(null);
    }
  }

  const headingId = `action-${action.id}`;
  const shownDescription = description === null ? null : (description ?? action.description);
  return (
    <form className={primary ? "action action--primary" : "action"} onSubmit={submit} aria-labelledby={headingId}>
      <h3 id={headingId}>
        {title ?? action.title}
        {shownDescription ? <InfoTip content={shownDescription} label={`About ${title ?? action.title}`} /> : null}
      </h3>
      {fields.map((field) => {
        const id = `${action.id}-${field.name}`;
        const hintId = field.hint ? `${id}-hint` : undefined;
        const value = values[field.name];
        const set = (v: string | boolean) => setValues((current) => ({ ...current, [field.name]: v }));
        return (
          <div key={field.name} className={field.kind === "boolean" ? "field field--inline" : field.kind === "longtext" || field.kind === "lines" || field.kind === "json" ? "field field--wide" : "field"}>
            <label htmlFor={id}>
              {field.label}
              {field.required ? "" : " (optional)"}
            </label>
            {field.kind === "boolean" ? (
              <input id={id} type="checkbox" checked={Boolean(value)} onChange={(e) => set(e.target.checked)} aria-describedby={hintId} />
            ) : field.kind === "choice" ? (
              <select id={id} value={typeof value === "string" ? value : ""} onChange={(e) => set(e.target.value)} aria-describedby={hintId}>
                <option value="">Choose…</option>
                {field.choices.map((choice) => (
                  <option key={choice} value={choice}>
                    {choice}
                  </option>
                ))}
              </select>
            ) : field.kind === "longtext" || field.kind === "lines" ? (
              <textarea id={id} value={typeof value === "string" ? value : ""} onChange={(e) => set(e.target.value)} aria-describedby={hintId} rows={4} />
            ) : (
              <input
                id={id}
                inputMode={field.kind === "number" || field.kind === "integer" ? "decimal" : undefined}
                value={typeof value === "string" ? value : ""}
                onChange={(e) => set(e.target.value)}
                aria-describedby={hintId}
              />
            )}
            {field.hint ? (
              <span id={hintId} className="panel__hint">
                {field.hint}
              </span>
            ) : null}
          </div>
        );
      })}
      <div className="row">
        <button type="submit" className="btn btn--primary" disabled={state === "running"} aria-busy={state === "running"}>
          {state === "running" ? "Running…" : submitLabel ?? "Run"}
        </button>
        {state === "running" && runId ? (
          <button type="button" className="btn" onClick={() => void client.cancelRun(runId).catch(() => undefined)}>
            Stop
          </button>
        ) : null}
      </div>
      {state === "failed" && message ? (
        <p className="notice" role="alert">
          Not done. {message}
        </p>
      ) : null}
      {state === "done" ? (
        <div role="status" className="result">
          <p className="result__title">Done{output && typeof output.message === "string" ? `. ${output.message}` : "."}</p>
          {output && Object.keys(output).length ? <OutputView value={output} /> : null}
        </div>
      ) : null}
    </form>
  );
}

/** Keys that identify stored things rather than tell the person anything. */
const QUIET_KEY = /^(id|revision|call_id)$|_id$|_ids$/;

function scalar(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return value.toLocaleString();
  return String(value);
}

/** A result in plain form: tables for lists of entries, lists for lists of words, nested
 *  details for groups. Never raw JSON (M1 review finding F03). */
export function ResultValue({ value, name = "" }: { value: unknown; name?: string }) {
  if (/artifact/i.test(name)) return <span>A file was made, but opening files from Alpha isn't available yet.</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <span className="panel__hint">None</span>;
    if (value.every((v) => v !== null && typeof v === "object" && !Array.isArray(v))) {
      const rows = value as Record<string, unknown>[];
      const columns = [...new Set(rows.flatMap((r) => Object.keys(r)))].filter((k) => !QUIET_KEY.test(k));
      return (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c} scope="col">
                    {humanize(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  {columns.map((c) => (
                    <td key={c}>
                      {row[c] !== null && typeof row[c] === "object" ? <ResultValue value={row[c]} name={c} /> : scalar(row[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    return (
      <ul className="output__list">
        {value.map((v, i) => (
          <li key={i}>{v !== null && typeof v === "object" ? <ResultValue value={v} /> : scalar(v)}</li>
        ))}
      </ul>
    );
  }
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).filter(([k]) => !QUIET_KEY.test(k));
    return (
      <dl className="output">
        {entries.map(([key, item]) => (
          <div key={key} className="output__row">
            <dt>{humanize(key)}</dt>
            <dd>
              <ResultValue value={item} name={key} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  return <span>{scalar(value)}</span>;
}

function OutputView({ value }: { value: Record<string, unknown> }) {
  // The message is already in the title; a result that says nothing else stays a sentence.
  const rest = Object.fromEntries(Object.entries(value).filter(([k]) => k !== "message" || typeof value[k] !== "string"));
  const visible = Object.keys(rest).filter((k) => !QUIET_KEY.test(k));
  if (!visible.length) return null;
  return <ResultValue value={rest} />;
}
