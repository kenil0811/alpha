import { Archive, Ellipsis, Plus, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { ModuleIcon } from "../ui/ModuleIcon";
import { InfoTip } from "../ui/InfoTip";
import { Button } from "../ui/Button";
import { IconButton } from "../ui/IconButton";
import { Tooltip } from "../ui/Tooltip";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../ui/DropdownMenu";
import { Markdown } from "../assistant/markdown";
import { usePoll } from "../core/usePoll";
import { ProjectEditDialog, ProjectMenuItems, type ProjectEdit } from "./ProjectMenu";
import { projectIcon } from "./projectIcons";
import "./pages.css";
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
  module: "From a sub project",
  assistant: "From a session",
  inferred: "Alpha worked it out",
};

/** The shared Markdown renderer knows paragraphs, bullets and inline marks; a plan's headings
 *  become bold lines and its numbered steps bullets (styled in pages.css as .projplan). */
function planMarkdown(text: string): string {
  return text
    .split("\n")
    .map((line) => line.replace(/^#{1,6}\s+(.*)$/, "**$1**").replace(/^(\s*)\d+[.)]\s+/, "$1- "))
    .join("\n");
}

// Core names an "Untitled project" (and picks its icon) after the first message; the page
// watches until then.
const UNTITLED = "Untitled project";

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
  onProject,
  onRemoved,
  facts,
  creation,
}: {
  client: SessionsClient;
  projectId: string;
  modules: AppSummary[];
  icons: Record<string, LucideIcon>;
  onOpenModule: (appId: string) => void;
  onOpenSession: (sessionId: string | null) => void;
  /** The project's name, modules or notes changed; the rail reloads. */
  onChanged?: () => void;
  /** Core renamed the project or gave it an icon on its own (seen while polling). */
  onProject?: (project: Project) => void;
  onRemoved?: () => void;
  /** Accepting or rejecting a project fact; absent when the runtime keeps no profile. */
  facts?: { accept: (factId: string) => Promise<unknown>; reject: (factId: string) => Promise<unknown>; forget: (factId: string) => Promise<unknown> };
  /** The project being made (its questions, options and build), shown above everything else. */
  creation?: React.ReactNode;
}) {
  const [project, setProject] = useState<Project | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [known, setKnown] = useState<{ facts: ProfileFact[]; suggestions: ProfileFact[] }>({ facts: [], suggestions: [] });
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<"name" | "goal" | "summary" | null>(null);
  const [draft, setDraft] = useState("");

  const [plan, setPlan] = useState<string | null>(null);
  const [dialog, setDialog] = useState<ProjectEdit | null>(null);

  const fetchAll = useCallback(
    () =>
      Promise.all([client.project(projectId), client.projectFile(projectId, "plan.md").catch(() => null)]),
    [client, projectId],
  );
  const apply = useCallback(([found, file]: Awaited<ReturnType<typeof fetchAll>>) => {
    setProject(found.project);
    setSessions(found.sessions.filter((s) => s.origin === "shell"));
    if (found.facts) setKnown(found.facts);
    setPlan(file?.text?.trim() ? file.text : null);
    setError(null);
  }, []);
  const load = useCallback(() => {
    fetchAll()
      .then(apply)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [fetchAll, apply]);
  useEffect(load, [load]);

  // While a session here works (or Core has yet to name the project), keep the plan, the name
  // and the icon current, and tell the rail when the name or icon moved.
  // ponytail: an untitled project nobody writes to polls every 3 s; a Core push event would end that.
  const working = sessions.some((s) => s.state === "thinking") || project?.name === UNTITLED;
  usePoll(
    working ? projectId : null,
    fetchAll,
    (result) => {
      const next = result[0].project;
      if (project && (next.name !== project.name || (next.icon ?? null) !== (project.icon ?? null))) onProject?.(next);
      apply(result);
    },
    3000,
  );

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

  const Icon = projectIcon(project?.icon);
  const onEnterBlur = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") e.currentTarget.blur();
    if (e.key === "Escape") setEditing(null);
  };

  return (
    <section className="page projpage" aria-labelledby="project-heading">
      <div className="modhead">
        <div className="modhead__title">
          <div className="modhead__ico" aria-hidden="true">
            <Icon size={18} strokeWidth={1.75} />
          </div>
          {editing === "name" ? (
            <input autoFocus aria-label="Project name" value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={() => void saveEdit()} onKeyDown={onEnterBlur} />
          ) : (
            <h2 id="project-heading" className="editable" onClick={() => startEdit("name")}>
              {project?.name ?? "Opening…"}
            </h2>
          )}
        </div>
        <div className="projpage__actions">
          {project ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <IconButton size="sm" aria-label="Project options">
                  <Ellipsis size={16} strokeWidth={1.75} />
                </IconButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <ProjectMenuItems onPick={(edit) => (edit === "rename" ? startEdit("name") : setDialog(edit))} />
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      </div>
      {editing === "goal" ? (
        <input autoFocus aria-label="Project goal" value={draft} placeholder="What this project is for" onChange={(e) => setDraft(e.target.value)} onBlur={() => void saveEdit()} onKeyDown={onEnterBlur} className="modhead__desc projpage__goalinput" />
      ) : project?.goal ? (
        <div className="modhead__desc editable" onClick={() => startEdit("goal")}>
          {project.goal}
        </div>
      ) : project ? (
        <Button variant="ghost" size="sm" className="projpage__addgoal" onClick={() => startEdit("goal")}>
          <Plus size={14} strokeWidth={1.75} aria-hidden="true" /> Add goal
        </Button>
      ) : null}
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}

      {creation}

      {plan ? (
        <section className="section" aria-label="Plan">
          <div className="section__head">
            <h2>Plan</h2>
          </div>
          <div className="card card--pad projplan">
            <Markdown text={planMarkdown(plan)} />
          </div>
        </section>
      ) : null}

      <div className="section">
        <div className="section__head">
          <h2>
            Alpha's notes
            <InfoTip content="What Alpha keeps in mind about this project, from your sessions. Yours to edit or clear." label="About Alpha's notes" />
          </h2>
        </div>
        {editing === "summary" ? (
          <textarea autoFocus aria-label="Alpha's notes" className="projpage__notesinput" value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={() => void saveEdit()} onKeyDown={(e) => { if (e.key === "Escape") setEditing(null); }} />
        ) : project?.summary ? (
          <div className="card card--pad">
            <p className="editable projpage__notes" onClick={() => startEdit("summary")}>
              {project.summary}
            </p>
          </div>
        ) : (
          <p className="projempty editable" onClick={() => startEdit("summary")}>
            Nothing yet
          </p>
        )}
      </div>

      <div className="section">
        <div className="section__head">
          <h2>Sub projects</h2>
          {inProject.length ? <span className="faint">{inProject.length}</span> : null}
          {elsewhere.length ? (
            <span className="section__right">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm">
                    <Plus size={14} strokeWidth={1.75} aria-hidden="true" /> Add sub project
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {elsewhere.map((m) => (
                    <DropdownMenuItem key={m.app_id} onSelect={() => void act(() => client.fileModule(m.app_id, projectId))}>
                      {m.name}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            </span>
          ) : null}
        </div>
        {inProject.length ? (
          <div className="card list" aria-label="Sub projects">
            {inProject.map((m) => (
              <div className="item" key={m.app_id}>
                <ModuleIcon icon={icons[m.app_id]} />
                <div className="item__body projrow__body">
                  <button type="button" className="linkbtn projrow__title" onClick={() => onOpenModule(m.app_id)}>
                    <b>{m.name}</b>
                  </button>
                  {m.description ? <InfoTip content={m.description} label={`About ${m.name}`} /> : null}
                </div>
                <Button variant="ghost" size="sm" className="projrow__action" onClick={() => void act(() => client.fileModule(m.app_id, null))} aria-label={`Take ${m.name} out of this project`}>
                  Take out
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <p className="projempty">None yet</p>
        )}
      </div>

      <div className="section">
        <div className="section__head">
          <h2>Sessions</h2>
          {sessions.length ? <span className="faint">{sessions.length}</span> : null}
        </div>
        {sessions.length ? (
          <div className="card list" aria-label="Sessions in this project">
            {sessions.map((s) => {
              const title = s.title ?? "Untitled session";
              return (
                <div className="item" key={s.session_id}>
                  <div className="item__body projrow__body">
                    <button type="button" className="linkbtn projrow__title" onClick={() => onOpenSession(s.session_id)}>
                      <b>{title}</b>
                    </button>
                    <div className="item__sub projrow__sub">
                      {s.turn_count} turn{s.turn_count === 1 ? "" : "s"} · {new Date(s.updated_at).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                      {s.state === "thinking" ? " · working" : ""}
                    </div>
                  </div>
                  <Tooltip content="Archive session">
                    <IconButton size="sm" className="projrow__action" aria-label={`Archive ${title}`} onClick={() => void act(() => client.updateSession(s.session_id, { archived: true }))}>
                      <Archive size={14} strokeWidth={1.75} />
                    </IconButton>
                  </Tooltip>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="projempty">None yet</p>
        )}
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
                <span className="row projpage__pair">
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
      <ProjectEditDialog
        client={client}
        project={project}
        edit={dialog}
        onClose={() => setDialog(null)}
        onChanged={(next) => {
          setProject(next);
          onChanged?.();
        }}
        onDeleted={() => onRemoved?.()}
      />
    </section>
  );
}
