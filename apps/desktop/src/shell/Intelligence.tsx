/**
 * Intelligence: what Alpha knows and can do across every module, in one place.
 *  - Second brain: the facts it holds about the person and what each module keeps.
 *  - Skills: reusable abilities that live outside any module; made, run and retired here.
 *  - Automations: every schedule across the modules, switchable in place.
 *  - Connections: which module reads which, switchable in place.
 * Nothing here is a module's own screen; each card links to where the detail lives.
 */
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  type AppSummary,
  type CoreClient,
  type ModuleConnection,
  type ProfileFact,
  type SchedulesClient,
  type ScheduleStatus,
  type SkillDraft,
  type SkillRun,
  type SkillSpec,
  isConnectionsClient,
  isProfileClient,
  isSkillsClient,
} from "../core/client";
import { humanize } from "../modules/useModule";

type Tab = "brain" | "skills" | "automations" | "connections";
const TABS: [Tab, string][] = [
  ["brain", "Second brain"],
  ["skills", "Skills"],
  ["automations", "Automations"],
  ["connections", "Connections"],
];

export function Intelligence({
  client,
  modules,
  icons,
  onOpenModule,
  onOpenAbout,
  onOpenAccounts,
}: {
  client: CoreClient;
  modules: AppSummary[];
  icons: Record<string, string>;
  onOpenModule: (appId: string) => void;
  onOpenAbout: () => void;
  onOpenAccounts: () => void;
}) {
  const [tab, setTab] = useState<Tab>("brain");
  return (
    <section className="page" aria-labelledby="intel-heading">
      <div className="modhead">
        <div className="modhead__title">
          <div>
            <h2 id="intel-heading">Intelligence</h2>
            <div className="faint">What Alpha knows and can do across your modules.</div>
          </div>
        </div>
      </div>
      <div className="subtabs" role="tablist" aria-label="Intelligence sections">
        {TABS.map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>
      {tab === "brain" ? <SecondBrain client={client} modules={modules} icons={icons} onOpenModule={onOpenModule} onOpenAbout={onOpenAbout} /> : null}
      {tab === "skills" ? isSkillsClient(client) ? <Skills client={client} /> : <p className="empty">Skills arrive with a newer runtime.</p> : null}
      {tab === "automations" ? <Automations client={client} modules={modules} icons={icons} onOpenModule={onOpenModule} /> : null}
      {tab === "connections" ? <ModuleLinks client={client} modules={modules} icons={icons} onOpenModule={onOpenModule} onOpenAccounts={onOpenAccounts} /> : null}
    </section>
  );
}

function shown(value: unknown): string {
  if (Array.isArray(value)) return value.map(String).join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value ?? "");
}

// ----- Second brain ---------------------------------------------------------------------

function SecondBrain({ client, modules, icons, onOpenModule, onOpenAbout }: { client: CoreClient; modules: AppSummary[]; icons: Record<string, string>; onOpenModule: (appId: string) => void; onOpenAbout: () => void }) {
  const [facts, setFacts] = useState<ProfileFact[] | null>(null);
  const [pending, setPending] = useState(0);
  useEffect(() => {
    if (!isProfileClient(client)) {
      setFacts([]);
      return;
    }
    let cancelled = false;
    client
      .profile()
      .then((view) => {
        if (cancelled) return;
        setFacts(view.facts);
        setPending(view.suggestions.length);
      })
      .catch(() => {
        if (!cancelled) setFacts([]);
      });
    return () => {
      cancelled = true;
    };
  }, [client]);
  return (
    <div className="intel">
      <div className="card card--pad intel__card">
        <div className="intel__head">
          <b>About you</b>
          <button type="button" className="btn btn--sm" onClick={onOpenAbout}>
            {pending ? `Manage (${pending} waiting for you)` : "Manage"}
          </button>
        </div>
        {facts === null ? (
          <p className="faint">Loading…</p>
        ) : facts.length ? (
          <dl className="intel__facts" aria-label="Facts Alpha knows">
            {facts.slice(0, 12).map((f) => (
              <div key={f.fact_id}>
                <dt>{humanize(f.field)}</dt>
                <dd>{shown(f.value)}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="faint">Nothing yet. Facts arrive from your conversations and modules, and you can add them on About you.</p>
        )}
      </div>
      <div className="card card--pad intel__card">
        <div className="intel__head">
          <b>What your modules keep</b>
        </div>
        {modules.length ? (
          <ul className="intel__modules">
            {modules.map((m) => (
              <li key={m.app_id}>
                <button type="button" className="linklike" onClick={() => onOpenModule(m.app_id)}>
                  <span aria-hidden="true">{icons[m.app_id] ?? "▦"}</span> {m.name}
                </button>
                <span className="faint">{m.description}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="faint">No modules yet.</p>
        )}
      </div>
    </div>
  );
}

// ----- Skills ---------------------------------------------------------------------------

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

function Skills({ client }: { client: CoreClient & { listSkills: () => Promise<SkillSpec[]>; createSkill: (d: SkillDraft) => Promise<SkillSpec>; retireSkill: (id: string) => Promise<void>; runSkill: (id: string, inputs: Record<string, unknown>) => Promise<SkillRun>; getSkill: (id: string) => Promise<{ skill: SkillSpec; runs: SkillRun[] }> } }) {
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

function SkillCard({ skill, onRun, onRetire }: { skill: SkillSpec; onRun: (inputs: Record<string, unknown>) => Promise<SkillRun>; onRetire: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
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
          <table className="table" aria-label="What it found">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c}>{humanize(c)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {run.items.map((item, i) => (
                <tr key={i}>
                  {columns.map((c) => (
                    <td key={c} title={shown(item[c])}>
                      {c === "source" && typeof item[c] === "string" && /^https?:/.test(item[c] as string) ? (
                        <a href={item[c] as string} target="_blank" rel="noreferrer">
                          {new URL(item[c] as string).hostname}
                        </a>
                      ) : (
                        shown(item[c])
                      )}
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
                <a href={String(e.url)} target="_blank" rel="noreferrer">
                  {String(e.title || e.url)}
                </a>
                {e.snippet ? <span className="faint"> — {String(e.snippet)}</span> : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

// ----- Automations ----------------------------------------------------------------------

function Automations({ client: core, modules, icons, onOpenModule }: { client: CoreClient; modules: AppSummary[]; icons: Record<string, string>; onOpenModule: (appId: string) => void }) {
  const client = core as CoreClient & SchedulesClient;
  const [rows, setRows] = useState<{ module: AppSummary; schedule: ScheduleStatus }[] | null>(null);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    if (!client.listSchedules) {
      setRows([]);
      return;
    }
    let cancelled = false;
    Promise.all(modules.map((m) => client.listSchedules!(m.app_id).then((all) => all.map((schedule) => ({ module: m, schedule }))).catch(() => [])))
      .then((groups) => {
        if (!cancelled) setRows(groups.flat());
      })
      .catch(() => {
        if (!cancelled) setRows([]);
      });
    return () => {
      cancelled = true;
    };
  }, [client, modules, version]);
  if (rows === null) return <p className="faint">Loading…</p>;
  if (!rows.length) return <p className="empty">Nothing runs on its own yet. A module that checks or reminds on a schedule appears here.</p>;
  return (
    <div className="card">
      <table className="table" aria-label="Automations">
        <thead>
          <tr>
            <th>Module</th>
            <th>What</th>
            <th>When</th>
            <th>Last ran</th>
            <th>On</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ module, schedule }) => (
            <tr key={`${module.app_id}:${schedule.id}`}>
              <td>
                <button type="button" className="linklike" onClick={() => onOpenModule(module.app_id)}>
                  <span aria-hidden="true">{icons[module.app_id] ?? "▦"}</span> {module.name}
                </button>
              </td>
              <td title={schedule.title}>{schedule.title}</td>
              <td>{schedule.when}</td>
              <td className={schedule.last_error ? "notice" : undefined} title={schedule.last_error ?? undefined}>
                {schedule.last_error ? "Failed last time" : schedule.last_run_at ? new Date(schedule.last_run_at).toLocaleString() : "Not yet"}
              </td>
              <td>
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={schedule.enabled}
                    aria-label={`${schedule.title} on`}
                    onChange={(e) => {
                      if (!client.setSchedule) return;
                      client
                        .setSchedule(module.app_id, schedule.id, e.target.checked)
                        .then(() => setVersion((v) => v + 1))
                        .catch(() => setVersion((v) => v + 1));
                    }}
                  />
                  <span />
                </label>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ----- Connections between modules ------------------------------------------------------

function ModuleLinks({ client, modules, icons, onOpenModule, onOpenAccounts }: { client: CoreClient; modules: AppSummary[]; icons: Record<string, string>; onOpenModule: (appId: string) => void; onOpenAccounts: () => void }) {
  const [rows, setRows] = useState<{ module: AppSummary; link: ModuleConnection }[] | null>(null);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    if (!isConnectionsClient(client)) {
      setRows([]);
      return;
    }
    let cancelled = false;
    Promise.all(modules.map((m) => client.connections(m.app_id).then((all) => all.map((link) => ({ module: m, link }))).catch(() => [])))
      .then((groups) => {
        if (!cancelled) setRows(groups.flat());
      })
      .catch(() => {
        if (!cancelled) setRows([]);
      });
    return () => {
      cancelled = true;
    };
  }, [client, modules, version]);
  return (
    <div className="stack">
      <div className="row">
        <p className="faint" style={{ flex: 1, margin: 0 }}>
          A module reads another only when it asked to and you left it on. Accounts and signed-in sites live on their own page.
        </p>
        <button type="button" className="btn btn--sm" onClick={onOpenAccounts}>
          Accounts and sites
        </button>
      </div>
      {rows === null ? <p className="faint">Loading…</p> : null}
      {rows && !rows.length ? <p className="empty">No module reads another yet. When one asks to, it shows here and in its Settings.</p> : null}
      {rows && rows.length ? (
        <div className="card">
          <table className="table" aria-label="Module connections">
            <thead>
              <tr>
                <th>Module</th>
                <th>Reads</th>
                <th>Why</th>
                <th>On</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ module, link }) => (
                <tr key={`${module.app_id}:${link.module}`}>
                  <td>
                    <button type="button" className="linklike" onClick={() => onOpenModule(module.app_id)}>
                      <span aria-hidden="true">{icons[module.app_id] ?? "▦"}</span> {module.name}
                    </button>
                  </td>
                  <td title={link.views.map((v) => v.id).join(", ")}>
                    {link.name}
                    {link.installed ? "" : " (not installed)"}
                    <span className="faint"> · {link.views.map((v) => v.collection ?? v.id).join(", ")}</span>
                  </td>
                  <td title={link.purpose}>{link.purpose}</td>
                  <td>
                    <label className="switch">
                      <input
                        type="checkbox"
                        checked={link.enabled}
                        disabled={!link.installed}
                        aria-label={`${module.name} reads ${link.name}`}
                        onChange={(e) => {
                          if (!isConnectionsClient(client)) return;
                          client
                            .setConnection(module.app_id, link.module, e.target.checked)
                            .then(() => setVersion((v) => v + 1))
                            .catch(() => setVersion((v) => v + 1));
                        }}
                      />
                      <span />
                    </label>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
