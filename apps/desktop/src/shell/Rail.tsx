import type { AppSummary, Project } from "../core/client";
import { ThemeControl, type Theme } from "./theme";

export type Surface =
  | { kind: "home" }
  | { kind: "activity" }
  | { kind: "connections" }
  | { kind: "about" }
  | { kind: "intelligence" }
  | { kind: "settings" }
  | { kind: "project"; projectId: string }
  | { kind: "module"; appId: string };

export function sameSurface(a: Surface, b: Surface): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === "module" && b.kind === "module") return a.appId === b.appId;
  if (a.kind === "project" && b.kind === "project") return a.projectId === b.projectId;
  return true;
}

export function Rail({
  surface,
  modules,
  projects = [],
  icons,
  runtime,
  onGo,
  onNew,
  onNewProject,
  theme,
  onTheme,
  collapsed = false,
  onToggleCollapsed,
}: {
  surface: Surface;
  modules: AppSummary[];
  /** The person's projects; a module sits under its project, the rest under "Your modules". */
  projects?: Project[];
  icons: Record<string, string>;
  runtime: "connecting" | "connected" | "unavailable";
  onGo: (surface: Surface) => void;
  onNew: () => void;
  onNewProject?: () => void;
  theme: Theme;
  onTheme: (next: Theme) => void;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}) {
  const item = (target: Surface, icon: string, label: string, extra?: { dot?: string; nested?: boolean }) => (
    <button
      key={target.kind === "module" ? `module:${target.appId}` : target.kind === "project" ? `project:${target.projectId}` : target.kind}
      type="button"
      className={`navbtn${sameSurface(surface, target) ? " navbtn--current" : ""}${extra?.nested ? " navbtn--nested" : ""}`}
      aria-current={sameSurface(surface, target) ? "page" : undefined}
      aria-label={label}
      title={collapsed ? label : undefined}
      onClick={() => onGo(target)}
    >
      <span className="navbtn__ico" aria-hidden="true">
        {icon}
      </span>
      <span className="navbtn__text">{label}</span>
      {extra?.dot ? <span className="navbtn__dot" style={{ background: extra.dot }} aria-hidden="true" /> : null}
    </button>
  );
  const byId = new Map(modules.map((m) => [m.app_id, m]));
  const filed = new Set(projects.flatMap((p) => p.modules));
  const unfiled = modules.filter((m) => !filed.has(m.app_id));
  return (
    <nav className={collapsed ? "rail rail--collapsed" : "rail"} aria-label="Alpha">
      <div className="brand">
        <div className="brand__mark" aria-hidden="true">
          A
        </div>
        <b>Alpha</b>
        {onToggleCollapsed ? (
          <button type="button" className="iconbtn rail__fold" onClick={onToggleCollapsed} aria-label={collapsed ? "Expand the sidebar" : "Collapse the sidebar"} aria-expanded={!collapsed} title={collapsed ? "Expand" : "Collapse"}>
            <span aria-hidden="true">{collapsed ? "»" : "«"}</span>
          </button>
        ) : null}
      </div>
      {item({ kind: "home" }, "⌂", "Home")}
      {item({ kind: "activity" }, "◷", "Activity")}
      {projects.length ? <div className="rail__group">Projects</div> : null}
      {projects.map((p) => (
        <div key={p.project_id} className="rail__project">
          {item({ kind: "project", projectId: p.project_id }, "◇", p.name)}
          {p.modules.map((appId) => {
            const m = byId.get(appId);
            return m ? item({ kind: "module", appId }, icons[appId] ?? "▦", m.name, { nested: true }) : null;
          })}
        </div>
      ))}
      <div className="rail__group">{projects.length ? "Other modules" : "Your modules"}</div>
      {modules.length === 0 ? <p className="faint" style={{ padding: "4px 10px" }}>None yet. Press New to make one.</p> : null}
      {unfiled.map((m) => item({ kind: "module", appId: m.app_id }, icons[m.app_id] ?? "▦", m.name))}
      <button type="button" className="navbtn navbtn--new" onClick={onNew} aria-label="New" title={collapsed ? "New module" : undefined}>
        <span className="navbtn__ico" aria-hidden="true" style={{ color: "var(--primary)" }}>
          +
        </span>
        <span className="navbtn__text">New</span>
      </button>
      {onNewProject ? (
        <button type="button" className="navbtn navbtn--quiet" onClick={onNewProject} aria-label="New project" title={collapsed ? "New project" : undefined}>
          <span className="navbtn__ico" aria-hidden="true">
            ◇
          </span>
          <span className="navbtn__text">New project</span>
        </button>
      ) : null}
      <div className="rail__spacer" />
      {collapsed ? null : (
        <div style={{ padding: "4px 10px 8px" }}>
          <ThemeControl theme={theme} onChange={onTheme} compact />
        </div>
      )}
      {item({ kind: "intelligence" }, "◈", "Intelligence")}
      {item({ kind: "about" }, "☺", "About you")}
      {item({ kind: "connections" }, "⛓", "Connections")}
      {item({ kind: "settings" }, "⚙", "Settings")}
      <div className={`rail__status rail__status--${runtime}`} role="status" title={collapsed ? (runtime === "connected" ? "Runtime connected" : runtime === "connecting" ? "Connecting to runtime" : "Runtime unavailable") : undefined}>
        <i aria-hidden="true" />
        <span className="rail__status-text">{runtime === "connected" ? "Runtime connected" : runtime === "connecting" ? "Connecting to runtime" : "Runtime unavailable"}</span>
      </div>
    </nav>
  );
}
