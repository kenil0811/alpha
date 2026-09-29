/** Skills: reusable abilities outside any module, made, run and retired here. */
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import type { CoreClient, SkillDraft, SkillRun, SkillSpec } from "../../core/client";
import { humanize } from "../../modules/useModule";
import { asLink, shown } from "./shared";
import "../../modules/views/views.css";

const EMPTY: SkillDraft = { title: "", description: "", kind: "procedure", instructions: "", module: null, action: null, inputs: [], produces: "", sources: [] };

function parseInputs(text: string): SkillDraft["inputs"] {
  return text
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => {
      const optional = p.endsWith("?");
      const name = (optional ? p.slice(0, -1) : p).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
      return { name, description: "", required: !optional };
    })
    .filter((i) => i.name);
}

export function Skills({ client }: { client: CoreClient & { listSkills: () => Promise<SkillSpec[]>; createSkill: (d: SkillDraft) => Promise<SkillSpec>; retireSkill: (id: string) => Promise<void>; runSkill: (id: string, inputs: Record<string, unknown>) => Promise<SkillRun>; getSkill: (id: string) => Promise<{ skill: SkillSpec; runs: SkillRun[] }> } }) {
  const [skills, setSkills] = useState<SkillSpec[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [making, setMaking] = useState(false);
  const load = useCallback(() => {
    client
      .listSkills()
      .then((all) => {
        setSkills(all);
        setError(null);
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e));
        setSkills([]);
      });
  }, [client]);
  useEffect(load, [load]);
  return (
    <div className="stack">
      <div className="row">
        <p className="faint" style={{ flex: 1, margin: 0 }}>
          A skill is a way Alpha knows to do one kind of job, on its own or when a sentence calls for it: find people to cold call, check a supplier, summarise a week.
        </p>
        <button type="button" className="btn btn--primary btn--sm" onClick={() => setMaking((v) => !v)} aria-expanded={making}>
          New skill
        </button>
      </div>
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
      {making ? (
        <SkillForm
          onCancel={() => setMaking(false)}
          onSave={async (draft) => {
            await client.createSkill(draft);
            setMaking(false);
            load();
          }}
        />
      ) : null}
      {skills === null ? <p className="faint">Loading…</p> : null}
      {skills && !skills.length && !making ? <p className="empty">No skills yet. Make one, or ask the assistant to teach Alpha how you do something.</p> : null}
      {(skills ?? []).map((s) => (
        <SkillCard
          key={s.id}
          skill={s}
          onRun={(inputs) => client.runSkill(s.id, inputs)}
          lastRun={() => client.getSkill(s.id).then((page) => page.runs[0] ?? null)}
          onRetire={async () => {
            await client.retireSkill(s.id);
            load();
          }}
        />
      ))}
    </div>
  );
}

function SkillForm({ onSave, onCancel }: { onSave: (draft: SkillDraft) => Promise<void>; onCancel: () => void }) {
  const [draft, setDraft] = useState(EMPTY);
  const [inputs, setInputs] = useState("");
  const [sources, setSources] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSave({ ...draft, inputs: parseInputs(inputs), sources: sources.split(",").map((s) => s.trim()).filter(Boolean) });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }
  const set = (key: keyof SkillDraft) => (e: { target: { value: string } }) => setDraft((d) => ({ ...d, [key]: e.target.value }));
  return (
    <form className="card card--pad stack" onSubmit={submit} aria-label="New skill">
      <div className="field">
        <label htmlFor="skill-title">Name</label>
        <input id="skill-title" type="text" value={draft.title} onChange={set("title")} placeholder="Find people to cold call" required maxLength={120} />
      </div>
      <div className="field">
        <label htmlFor="skill-desc">What it does</label>
        <input id="skill-desc" type="text" value={draft.description} onChange={set("description")} placeholder="Finds people worth calling in an industry and says why each fits" required maxLength={1000} />
      </div>
      <div className="field">
        <label htmlFor="skill-how">How Alpha does it, step by step</label>
        <textarea id="skill-how" value={draft.instructions} onChange={set("instructions")} placeholder={"Search for operations leaders in the industry and city.\nRead each person's page or company site.\nKeep only people who own the buying decision.\nFor each: name, role, company, one line on why they fit, the source."} required maxLength={6000} />
      </div>
      <div className="intel__grid">
        <div className="field">
          <label htmlFor="skill-inputs">It needs (comma-separated; a ? marks optional)</label>
          <input id="skill-inputs" type="text" value={inputs} onChange={(e) => setInputs(e.target.value)} placeholder="industry, city?" />
        </div>
        <div className="field">
          <label htmlFor="skill-sources">Sources it may read</label>
          <input id="skill-sources" type="text" value={sources} onChange={(e) => setSources(e.target.value)} placeholder="LinkedIn, company websites" />
        </div>
        <div className="field">
          <label htmlFor="skill-produces">It produces</label>
          <input id="skill-produces" type="text" value={draft.produces} onChange={set("produces")} placeholder="a list of people with name, role, company, why, source" maxLength={400} />
        </div>
      </div>
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
      <div className="row">
        <button type="submit" className="btn btn--primary" disabled={busy}>
          {busy ? "Saving…" : "Save skill"}
        </button>
        <button type="button" className="btn" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function SkillCard({ skill, onRun, onRetire, lastRun }: { skill: SkillSpec; onRun: (inputs: Record<string, unknown>) => Promise<SkillRun>; onRetire: () => Promise<void>; lastRun: () => Promise<SkillRun | null> }) {
  const [open, setOpen] = useState(false);
  const [previous, setPrevious] = useState<SkillRun | null>(null);
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    lastRun()
      .then((run) => {
        if (!cancelled) setPrevious(run);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the loader is stable per skill
  }, [open, skill.id]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<SkillRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputs = skill.inputs ?? [];
  async function run(e: FormEvent) {
    e.preventDefault();
    setRunning(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = {};
      for (const i of inputs) if (values[i.name]?.trim()) payload[i.name] = values[i.name].trim();
      setResult(await onRun(payload));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }
  return (
    <article className="card card--pad skill" aria-label={skill.title}>
      <div className="intel__head">
        <div>
          <b>{skill.title}</b>
          <div className="faint">{skill.description}</div>
        </div>
        <div className="row">
          <span className="pill pill--gray">{skill.kind === "code" ? `Runs ${skill.module}` : "Procedure"}</span>
          <button type="button" className="btn btn--sm" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            {open ? "Close" : "Run"}
          </button>
          <button type="button" className="btn btn--sm btn--ghost btn--danger" onClick={onRetire} aria-label={`Retire ${skill.title}`}>
            Retire
          </button>
        </div>
      </div>
      {inputs.length || skill.sources?.length ? (
        <div className="faint skill__meta">
          {inputs.length ? <span>Needs: {inputs.map((i) => (i.required ? i.name : `${i.name} (optional)`)).join(", ")}</span> : null}
          {skill.sources?.length ? <span>Reads: {skill.sources.join(", ")}</span> : null}
        </div>
      ) : null}
      {open ? (
        <form className="stack skill__run" onSubmit={run} aria-label={`Run ${skill.title}`}>
          {inputs.length ? (
            <div className="intel__grid">
              {inputs.map((i) => (
                <div className="field" key={i.name}>
                  <label htmlFor={`${skill.id}-${i.name}`}>
                    {humanize(i.name)}
                    {i.required ? "" : " (optional)"}
                  </label>
                  <input id={`${skill.id}-${i.name}`} type="text" value={values[i.name] ?? ""} onChange={(e) => setValues((v) => ({ ...v, [i.name]: e.target.value }))} required={i.required} />
                </div>
              ))}
            </div>
          ) : null}
          <div className="row">
            <button type="submit" className="btn btn--primary btn--sm" disabled={running}>
              {running ? "Working…" : "Run now"}
            </button>
            {running ? <span className="faint">Alpha is searching and reading; this can take a minute or two.</span> : null}
          </div>
          {error ? (
            <p className="notice" role="alert">
              {error}
            </p>
          ) : null}
          {result ? <RunResult run={result} /> : null}
          {!result && previous ? (
            <div className="skill__previous">
              <div className="faint">Last time ({new Date(previous.started_at).toLocaleString()}{Object.keys(previous.inputs).length ? `, ${Object.values(previous.inputs).map(String).join(", ")}` : ""}):</div>
              <RunResult run={previous} />
            </div>
          ) : null}
        </form>
      ) : null}
    </article>
  );
}

function RunResult({ run }: { run: SkillRun }) {
  const columns = useMemo(() => {
    const keys: string[] = [];
    for (const item of run.items) for (const k of Object.keys(item)) if (!keys.includes(k)) keys.push(k);
    return keys.slice(0, 6);
  }, [run.items]);
  return (
    <div className="skill__result" role="status">
      <p className={run.state === "failed" ? "notice" : "notice notice--quiet"}>{run.summary}</p>
      {run.items.length ? (
        <div className="card" style={{ overflow: "auto" }}>
          <table className="table dv-table" aria-label="What it found">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c}>{humanize(c)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {run.items.map((item, i) => (
                <tr key={i} className="dv-row">
                  {columns.map((c) => (
                    <td key={c} title={shown(item[c])}>
                      {(() => {
                        const link = asLink(item[c]);
                        return link ? (
                          <a href={link.href} target="_blank" rel="noreferrer">
                            {link.label}
                          </a>
                        ) : (
                          shown(item[c])
                        );
                      })()}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {run.evidence.length ? (
        <details>
          <summary className="faint">Where it looked ({run.evidence.length})</summary>
          <ul className="skill__evidence">
            {run.evidence.map((e, i) => (
              <li key={i}>
                {asLink(e.url) ? (
                  <a href={String(e.url)} target="_blank" rel="noreferrer">
                    {String(e.title || e.url)}
                  </a>
                ) : (
                  <span>{String(e.title || e.url || "")}</span>
                )}
                {e.snippet ? <span className="faint"> — {String(e.snippet)}</span> : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

