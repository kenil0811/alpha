import { Home as HomeIcon, Clock, Link2, Settings as SettingsIcon, Plus, PanelLeftClose, PanelLeftOpen, Boxes, type LucideIcon } from "lucide-react";
import type { AppSummary } from "../core/client";
import { Tooltip } from "../ui/Tooltip";

export type Surface =
  | { kind: "home" }
  | { kind: "activity" }
  | { kind: "connections" }
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
  collapsed = false,
  onToggleCollapsed,
}: {
  surface: Surface;
  modules: AppSummary[];
  icons: Record<string, LucideIcon>;
  runtime: "connecting" | "connected" | "unavailable";
  onGo: (surface: Surface) => void;
  onNew: () => void;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}) {
  const item = (target: Surface, Icon: LucideIcon, label: string) => (
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
        <Icon size={16} strokeWidth={1.75} />
      </span>
      <span className="navbtn__text">{label}</span>
    </button>
  );
  const runtimeLabel = runtime === "connected" ? "Runtime connected" : runtime === "connecting" ? "Connecting to runtime" : "Runtime unavailable";
  return (
    <nav className={collapsed ? "rail rail--collapsed" : "rail"} aria-label="Alpha">
      <div className="brand">
        <Tooltip content={runtimeLabel}>
          <div className={`brand__mark brand__mark--${runtime}`} role="status">
            <span aria-hidden="true">A</span>
            <span className="sr-only">{runtimeLabel}</span>
          </div>
        </Tooltip>
        <b>Alpha</b>
        {onToggleCollapsed ? (
          <button type="button" className="iconbtn rail__fold" onClick={onToggleCollapsed} aria-label={collapsed ? "Expand the sidebar" : "Collapse the sidebar"} aria-expanded={!collapsed}>
            {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
        ) : null}
      </div>
      {item({ kind: "home" }, HomeIcon, "Home")}
      {modules.map((m) => item({ kind: "module", appId: m.app_id }, icons[m.app_id] ?? Boxes, m.name))}
      <button type="button" className="navbtn navbtn--new" onClick={onNew} aria-label="New module" title={collapsed ? "New module" : undefined}>
        <span className="navbtn__ico" aria-hidden="true" style={{ color: "var(--primary)" }}>
          <Plus size={16} strokeWidth={1.75} />
        </span>
        <span className="navbtn__text">New</span>
      </button>
      <div className="rail__spacer" />
      {item({ kind: "activity" }, Clock, "Activity")}
      {item({ kind: "connections" }, Link2, "Connections")}
      {item({ kind: "settings" }, SettingsIcon, "Settings")}
    </nav>
  );
}
