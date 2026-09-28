import type { AppSummary } from "../core/client";
import { ThemeControl, type Theme } from "./theme";

export type Surface =
  | { kind: "home" }
  | { kind: "activity" }
  | { kind: "connections" }
  | { kind: "about" }
  | { kind: "intelligence" }
  | { kind: "settings" }
  | { kind: "module"; appId: string };

export function sameSurface(a: Surface, b: Surface): boolean {
  return a.kind === b.kind && (a.kind !== "module" || b.kind !== "module" || a.appId === b.appId);
}

export function Rail({
  surface,
  modules,
  icons,
  runtime,
  onGo,
  onNew,
  theme,
  onTheme,
  collapsed = false,
  onToggleCollapsed,
}: {
  surface: Surface;
  modules: AppSummary[];
  icons: Record<string, string>;
  runtime: "connecting" | "connected" | "unavailable";
  onGo: (surface: Surface) => void;
  onNew: () => void;
  theme: Theme;
  onTheme: (next: Theme) => void;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}) {
  const item = (target: Surface, icon: string, label: string, dot?: string) => (
    <button
      key={target.kind === "module" ? `module:${target.appId}` : target.kind}
      type="button"
      className={sameSurface(surface, target) ? "navbtn navbtn--current" : "navbtn"}
      aria-current={sameSurface(surface, target) ? "page" : undefined}
      aria-label={label}
      title={collapsed ? label : undefined}
      onClick={() => onGo(target)}
    >
      <span className="navbtn__ico" aria-hidden="true">
        {icon}
      </span>
      <span className="navbtn__text">{label}</span>
      {dot ? <span className="navbtn__dot" style={{ background: dot }} aria-hidden="true" /> : null}
    </button>
  );
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
      <div className="rail__group">Your modules</div>
      {modules.length === 0 ? <p className="faint" style={{ padding: "4px 10px" }}>None yet. Press New to make one.</p> : null}
      {modules.map((m) => item({ kind: "module", appId: m.app_id }, icons[m.app_id] ?? "▦", m.name))}
      <button type="button" className="navbtn navbtn--new" onClick={onNew} aria-label="New" title={collapsed ? "New module" : undefined}>
        <span className="navbtn__ico" aria-hidden="true" style={{ color: "var(--primary)" }}>
          +
        </span>
        <span className="navbtn__text">New</span>
      </button>
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
