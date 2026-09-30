import { Folder, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { ModuleIcon } from "../ui/ModuleIcon";
import { InfoTip } from "../ui/InfoTip";
/**
 * A project's page: its goal in the person's words, Alpha's own notes on it (editable, never
 * silently used to change anything), the modules filed under it, its sessions, and the facts
 * that hold only inside this project (accepted and waiting for a yes).
 */
import { useCallback, useEffect, useState } from "react";
import type { AppSummary, ProfileFact, Project, SessionsClient, SessionSummary } from "../core/client";
import { humanize } from "../modules/useModule";
import "../modules/module.css";

const SOURCE: Record<ProfileFact["provenance"], string> = {
  person: "You said so",
  module: "From a module",
  assistant: "From a session",
  inferred: "Alpha worked it out",
};

function shown(value: unknown): string {
  if (Array.isArray(value)) return value.map(String).join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value ?? "");
}

export function ProjectPage({
  client,
  projectId,
  modules,
  icons,
  onOpenModule,
  onOpenSession,
  onChanged,
  onRemoved,
  facts,
}: {
  client: SessionsClient;
  projectId: string;
  modules: AppSummary[];
  icons: Record<string, LucideIcon>;
  onOpenModule: (appId: string) => void;
  onOpenSession: (sessionId: string | null) => void;
  /** The project's name, modules or notes changed; the rail reloads. */
  onChanged?: () => void;
  onRemoved?: () => void;
  /** Accepting or rejecting a project fact; absent when the runtime keeps no profile. */
  facts?: { accept: (factId: string) => Promise<unknown>; reject: (factId: string) => Promise<unknown>; forget: (factId: string) => Promise<unknown> };
}) {
  const [project, setProject] = useState<Project | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [known, setKnown] = useState<{ facts: ProfileFact[]; suggestions: ProfileFact[] }>({ facts: [], suggestions: [] });
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<"name" | "goal" | "summary" | null>(null);
  const [draft, setDraft] = useState("");

  const load = useCallback(() => {
    client
      .project(projectId)
      .then((found) => {
        setProject(found.project);
        setSessions(found.sessions.filter((s) => s.origin === "shell"));
        if (found.facts) setKnown(found.facts);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [client, projectId]);
  useEffect(load, [load]);

  async function act(work: () => Promise<unknown>) {
    try {
      await work();
      load();
      onChanged?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  function startEdit(what: "name" | "goal" | "summary") {
    if (!project) return;
    setEditing(what);
    setDraft(project[what] ?? "");
  }
  async function saveEdit() {
    const what = editing;
    setEditing(null);
    if (!what || !project) return;
    const value = draft.trim();
    if (what === "name" && !value) return;
    if ((project[what] ?? "") === value) return;
    await act(() => client.updateProject(projectId, { [what]: value }));
  }

  const mine = new Set(project?.modules ?? []);
  const inProject = modules.filter((m) => mine.has(m.app_id));
  const elsewhere = modules.filter((m) => !mine.has(m.app_id));

  return (
    <section className="page" aria-labelledby="project-heading">
      <div className="modhead">
        <div className="modhead__title">
          <div className="modhead__ico" aria-hidden="true">
            <Folder size={18} strokeWidth={1.75} />
          </div>
          {editing === "name" ? (
            <input autoFocus aria-label="Project name" value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={() => void saveEdit()} onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); if (e.key === "Escape") setEditing(null); }} />
          ) : (
            <h2 id="project-heading" className="editable" onClick={() => startEdit("name")} title="Click to rename">
              {project?.name ?? "Opening…"}
            </h2>
          )}
        </div>
        <div className="row">
          <button type="button" className="btn btn--sm btn--primary" onClick={() => onOpenSession(null)}>
            New session
          </button>
          {project && onRemoved ? (
            <button type="button" className="btn btn--sm" onClick={() => void act(() => client.updateProject(projectId, { archived: true })).then(onRemoved)}>
              Archive
            </button>
          ) : null}
        </div>
      </div>
      {editing === "goal" ? (
        <input autoFocus aria-label="Project goal" value={draft} placeholder="What this project is for, in your words" onChange={(e) => setDraft(e.target.value)} onBlur={() => void saveEdit()} onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); if (e.key === "Escape") setEditing(null); }} className="modhead__desc" style={{ width: "100%" }} />
      ) : (
        <div className="modhead__desc editable" onClick={() => startEdit("goal")} title="Click to edit the goal">
          {project?.goal ?? "Add a goal: what this project is for, in your words."}
        </div>
      )}
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}

      <div className="section" style={{ marginTop: 0 }}>
        <div className="section__head">
          <h2>
            Alpha's notes
            <InfoTip content="What Alpha keeps in mind about this project, from your sessions. Yours to edit or clear." label="About Alpha's notes" />
          </h2>
        </div>
        <div className="card card--pad">
          {editing === "summary" ? (
            <textarea autoFocus aria-label="Alpha's notes" value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={() => void saveEdit()} onKeyDown={(e) => { if (e.key === "Escape") setEditing(null); }} style={{ width: "100%", minHeight: 96 }} />
          ) : (
            <p className="editable" style={{ margin: 0, whiteSpace: "pre-wrap" }} onClick={() => startEdit("summary")} title="Click to edit">
              {project?.summary ?? <span className="faint">Nothing yet. Notes appear as sessions in this project go on.</span>}
            </p>
          )}
        </div>
      </div>

      <div className="section">
        <div className="section__head">
          <h2>Modules</h2>
          <span className="faint">{inProject.length ? `${inProject.length} in this project` : "None filed here yet."}</span>
          {elsewhere.length ? (
            <select
              className="section__right"
              aria-label="Add a module to this project"
              value=""
              onChange={(e) => {
                const appId = e.target.value;
                if (appId) void act(() => client.fileModule(appId, projectId));
              }}
            >
              <option value="">Add a module…</option>
              {elsewhere.map((m) => (
                <option key={m.app_id} value={m.app_id}>
                  {m.name}
                </option>
              ))}
            </select>
          ) : null}
        </div>
        <div className="card list" aria-label="Modules in this project">
          {inProject.map((m) => (
            <div className="item" key={m.app_id}>
              <ModuleIcon icon={icons[m.app_id]} />
              <div className="item__body">
                <button type="button" className="linkbtn" onClick={() => onOpenModule(m.app_id)}>
                  <b>{m.name}</b>
                </button>
                {m.description ? <InfoTip content={m.description} label={`About ${m.name}`} /> : null}
              </div>
              <button type="button" className="btn btn--sm btn--ghost" onClick={() => void act(() => client.fileModule(m.app_id, null))} aria-label={`Take ${m.name} out of this project`}>
                Take out
              </button>
            </div>
          ))}
          {!inProject.length ? <p className="empty">Add a module above, or ask for a new one in a session here and it is filed under this project.</p> : null}
        </div>
      </div>

      <div className="section">
        <div className="section__head">
          <h2>Sessions</h2>
          <span className="faint">{sessions.length ? `${sessions.length} so far` : "None yet."}</span>
        </div>
        <div className="card list" aria-label="Sessions in this project">
          {sessions.map((s) => (
            <div className="item" key={s.session_id}>
              <div className="item__body">
                <button type="button" className="linkbtn" onClick={() => onOpenSession(s.session_id)}>
                  <b>{s.title ?? "Untitled session"}</b>
                </button>
                <div className="item__sub">
                  {s.turn_count} turn{s.turn_count === 1 ? "" : "s"} · {new Date(s.updated_at).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                  {s.state === "thinking" ? " · working" : ""}
                </div>
              </div>
              <button type="button" className="btn btn--sm btn--ghost" aria-label={`Archive ${s.title ?? "this session"}`} onClick={() => void act(() => client.updateSession(s.session_id, { archived: true }))}>
                Archive
              </button>
            </div>
          ))}
          {!sessions.length ? <p className="empty">Start one with New session; the assistant then knows it is about this project.</p> : null}
        </div>
      </div>

      {known.suggestions.length && facts ? (
        <div className="section">
          <div className="section__head">
            <h2>
              Waiting for your yes
              <InfoTip content="Things Alpha thinks hold for this project; nothing uses them until you accept." label="About suggested project facts" />
            </h2>
          </div>
          <div className="card list" aria-label="Suggested project facts">
            {known.suggestions.map((s) => (
              <div className="item" key={s.fact_id}>
                <div className="item__body">
                  <b>
                    {humanize(s.field)}: {shown(s.value)}
                  </b>
                  <div className="item__sub">
                    {SOURCE[s.provenance]}
                    {s.why ? ` · ${s.why}` : ""}
                  </div>
                </div>
                <span className="row" style={{ gap: 6 }}>
                  <button type="button" className="btn btn--sm btn--primary" onClick={() => void act(() => facts.accept(s.fact_id))}>
                    Yes, that's right
                  </button>
                  <button type="button" className="btn btn--sm" onClick={() => void act(() => facts.reject(s.fact_id))}>
                    No
                  </button>
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {known.facts.length ? (
        <div className="section">
          <div className="section__head">
            <h2>
              Facts for this project
              <InfoTip content="Hold here only; About you keeps what holds everywhere." label="About project facts" />
            </h2>
          </div>
          <div className="card list" aria-label="Project facts">
            {known.facts.map((f) => (
              <div className="item" key={f.fact_id}>
                <div className="item__body">
                  <b>
                    {humanize(f.field)}: {shown(f.value)}
                  </b>
                  <div className="item__sub">{SOURCE[f.provenance]}</div>
                </div>
                {facts ? (
                  <button type="button" className="btn btn--sm btn--ghost" aria-label={`Forget ${humanize(f.field)}`} onClick={() => void act(() => facts.forget(f.fact_id))}>
                    <X size={14} strokeWidth={1.75} aria-hidden="true" />
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
