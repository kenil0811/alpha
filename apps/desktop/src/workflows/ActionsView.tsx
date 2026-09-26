/**
 * The shell-provided view for an App without its own screen: each action the person may run,
 * with a form from its declared inputs, and its result in plain words. Runs go through Core
 * like any other, and the result shown is only what the platform reports.
 */
import { useState, type FormEvent } from "react";
import type { ActionSummary, OperationOutcome, WorkflowsClient } from "../core/client";
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

export function ActionsView({
  client,
  appId,
  actions,
  onChanged,
}: {
  client: WorkflowsClient;
  appId: string;
  actions: ActionSummary[];
  onChanged: () => void;
}) {
  const runnable = actions.filter((a) => a.invocable_from.includes("manual") || a.invocable_from.includes("ui"));
  if (!runnable.length) return <p className="panel__hint">This App has nothing to run by hand.</p>;
  return (
    <div className="actions">
      {runnable.map((action) => (
        <ActionForm key={action.id} client={client} appId={appId} action={action} onChanged={onChanged} />
      ))}
    </div>
  );
}

function ActionForm({
  client,
  appId,
  action,
  onChanged,
}: {
  client: WorkflowsClient;
  appId: string;
  action: ActionSummary;
  onChanged: () => void;
}) {
  const fields = formFields(action.input_schema);
  const [values, setValues] = useState<FormValues>({});
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
  return (
    <form className="action" onSubmit={submit} aria-labelledby={headingId}>
      <h3 id={headingId}>{action.title}</h3>
      <p className="panel__hint">{action.description}</p>
      {fields.map((field) => {
        const id = `${action.id}-${field.name}`;
        const hintId = field.hint ? `${id}-hint` : undefined;
        const value = values[field.name];
        const set = (v: string | boolean) => setValues((current) => ({ ...current, [field.name]: v }));
        return (
          <div key={field.name} className={field.kind === "boolean" ? "field field--inline" : "field"}>
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
            ) : field.kind === "longtext" || field.kind === "json" ? (
              <textarea id={id} value={typeof value === "string" ? value : ""} onChange={(e) => set(e.target.value)} aria-describedby={hintId} rows={field.kind === "json" ? 3 : 5} />
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
        <button type="submit" className="button button--primary" disabled={state === "running"} aria-busy={state === "running"}>
          {state === "running" ? "Running…" : "Run"}
        </button>
        {state === "running" && runId ? (
          <button type="button" className="button" onClick={() => void client.cancelRun(runId).catch(() => undefined)}>
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
          <p className="result__title">Done.</p>
          {output && Object.keys(output).length ? <OutputView value={output} /> : null}
        </div>
      ) : null}
    </form>
  );
}

function OutputView({ value }: { value: Record<string, unknown> }) {
  return (
    <dl className="output">
      {Object.entries(value).map(([key, item]) => (
        <div key={key} className="output__row">
          <dt>{humanize(key)}</dt>
          <dd>{typeof item === "object" && item !== null ? <pre>{JSON.stringify(item, null, 2)}</pre> : String(item)}</dd>
        </div>
      ))}
    </dl>
  );
}
