import { useCallback, useRef, useState } from "react";
import { Home as HomeIcon, Settings as SettingsIcon, Plus, Boxes, MoreVertical, type LucideIcon } from "lucide-react";
import type { AppSummary } from "../core/client";
import { Tooltip } from "../ui/Tooltip";
import { CollapseToggleButton, ResizeHandle, type PanelControl } from "../ui/panel";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from "../ui/DropdownMenu";

/** Route paths the rail links to. Kept as a small helper rather than a routing dependency here,
 *  so Rail stays a plain component the App wires to react-router (it calls `navigate`/reads
 *  `pathname`, both passed in as props — no useNavigate/useLocation import needed in this file's
 *  own tests). */
const WORKSPACE_KEY = "alpha.workspace.name";

export type Surface = { kind: "home" } | { kind: "activity" } | { kind: "settings"; section?: string } | { kind: "module"; appId: string };

export function surfacePath(s: Surface): string {
  switch (s.kind) {
    case "home":
      return "/";
    case "activity":
      return "/activity";
    case "settings":
      return s.section ? `/settings/${encodeURIComponent(s.section)}` : "/settings";
    case "module":
      return `/m/${encodeURIComponent(s.appId)}`;
  }
}

export function sameSurface(a: Surface, b: Surface): boolean {
  return a.kind === b.kind && (a.kind !== "module" || b.kind !== "module" || a.appId === b.appId);
}

const HIDDEN_KEY = "alpha.rail.hiddenModules";
const ORDER_KEY = "alpha.rail.moduleOrder";

function readList(key: string): string[] {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}
function writeList(key: string, value: string[]): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* per-window convenience only */
  }
}

/** Orders modules by the person's saved drag order (unknown modules keep their server order,
 *  appended after any known ones), then drops any hidden from the visible list. */
function useModuleOrdering(modules: AppSummary[]) {
  const [order, setOrder] = useState<string[]>(() => readList(ORDER_KEY));
  const [hidden, setHidden] = useState<string[]>(() => readList(HIDDEN_KEY));

  const ordered = [...modules].sort((a, b) => {
    const ia = order.indexOf(a.app_id);
    const ib = order.indexOf(b.app_id);
    if (ia === -1 && ib === -1) return 0;
    if (ia === -1) return 1;
    if (ib === -1) return -1;
    return ia - ib;
  });

  const reorder = useCallback(
    (dragId: string, dropId: string) => {
      const ids = ordered.map((m) => m.app_id);
      const from = ids.indexOf(dragId);
      const to = ids.indexOf(dropId);
      if (from === -1 || to === -1 || from === to) return;
      const next = [...ids];
      next.splice(from, 1);
      next.splice(to, 0, dragId);
      setOrder(next);
      writeList(ORDER_KEY, next);
    },
    [ordered],
  );

  const hide = useCallback((appId: string) => {
    setHidden((current) => {
      const next = current.includes(appId) ? current : [...current, appId];
      writeList(HIDDEN_KEY, next);
      return next;
    });
  }, []);
  const showAll = useCallback(() => {
    setHidden([]);
    writeList(HIDDEN_KEY, []);
  }, []);

  const visible = ordered.filter((m) => !hidden.includes(m.app_id));
  const hiddenCount = hidden.filter((id) => modules.some((m) => m.app_id === id)).length;

  return { visible, hiddenCount, reorder, hide, showAll };
}

export function Rail({
  surface,
  modules,
  icons,
  runtime,
  onGo,
  onNew,
  panel,
}: {
  surface: Surface;
  modules: AppSummary[];
  icons: Record<string, LucideIcon>;
  runtime: "connecting" | "connected" | "unavailable";
  onGo: (surface: Surface) => void;
  onNew: () => void;
  panel: PanelControl;
}) {
  const collapsed = panel.collapsed;
  const { visible, hiddenCount, reorder, hide, showAll } = useModuleOrdering(modules);
  const dragId = useRef<string | null>(null);

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

  const moduleRow = (m: AppSummary) => {
    const target: Surface = { kind: "module", appId: m.app_id };
    const current = sameSurface(surface, target);
    return (
      <div
        key={m.app_id}
        className={`navrow${current ? " navrow--current" : ""}`}
        draggable={!collapsed}
        onDragStart={() => {
          dragId.current = m.app_id;
        }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          if (dragId.current) reorder(dragId.current, m.app_id);
          dragId.current = null;
        }}
        onContextMenu={(e) => e.preventDefault()}
      >
        <button
          type="button"
          className={current ? "navbtn navbtn--current navrow__main" : "navbtn navrow__main"}
          aria-current={current ? "page" : undefined}
          aria-label={m.name}
          title={collapsed ? m.name : undefined}
          onClick={() => onGo(target)}
        >
          <span className="navbtn__ico" aria-hidden="true">
            {(() => {
              const Icon = icons[m.app_id] ?? Boxes;
              return <Icon size={16} strokeWidth={1.75} />;
            })()}
          </span>
          <span className="navbtn__text">{m.name}</span>
        </button>
        {!collapsed ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button type="button" className="iconbtn iconbtn--sm navrow__menu" aria-label={`${m.name} options`}>
                <MoreVertical size={14} />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem onSelect={() => onGo(target)}>Open</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => hide(m.app_id)}>Hide from sidebar</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
    );
  };

  const [workspace, setWorkspace] = useState(() => localStorage.getItem(WORKSPACE_KEY) || "Alpha");
  const [renaming, setRenaming] = useState(false);
  const saveWorkspace = (value: string) => {
    const name = value.trim();
    // ponytail: name kept on this Mac only; move to a Core setting when workspaces sync.
    if (name) {
      setWorkspace(name);
      localStorage.setItem(WORKSPACE_KEY, name);
    }
    setRenaming(false);
  };
  const runtimeLabel = runtime === "connected" ? "Runtime connected" : runtime === "connecting" ? "Connecting to runtime" : "Runtime unavailable";
  return (
    <nav className={collapsed ? "rail rail--collapsed" : "rail"} aria-label="Alpha" style={{ width: panel.displayWidth }}>
      <div className="brand" data-tauri-drag-region>
        <Tooltip content={runtimeLabel}>
          <div className={`brand__mark brand__mark--${runtime}`} role="status">
            <span aria-hidden="true">{(workspace.trim()[0] ?? "A").toUpperCase()}</span>
            <span className="sr-only">{runtimeLabel}</span>
          </div>
        </Tooltip>
        {renaming ? (
          <input
            className="brand__input"
            aria-label="Workspace name"
            defaultValue={workspace}
            maxLength={40}
            autoFocus
            onFocus={(e) => e.target.select()}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
              if (e.key === "Escape") setRenaming(false);
            }}
            onBlur={(e) => saveWorkspace(e.target.value)}
          />
        ) : (
          <button type="button" className="brand__name" title="Rename workspace" aria-label={`Workspace: ${workspace}. Rename`} onClick={() => setRenaming(true)}>
            {workspace}
          </button>
        )}
        <CollapseToggleButton side="left" collapsed={collapsed} onClick={panel.toggleCollapsed} controls="rail-body" className="rail__fold" />
      </div>
      <div id="rail-body" className="rail__body">
        {item({ kind: "home" }, HomeIcon, "Home")}
        {visible.map(moduleRow)}
        <button type="button" className="navbtn navbtn--new" onClick={onNew} aria-label="New module" title={collapsed ? "New module" : undefined}>
          <span className="navbtn__ico" aria-hidden="true" style={{ color: "var(--primary)" }}>
            <Plus size={16} strokeWidth={1.75} />
          </span>
          <span className="navbtn__text">New</span>
        </button>
        {!collapsed && hiddenCount > 0 ? (
          <button type="button" className="navbtn navbtn--hidden" onClick={showAll}>
            <span className="navbtn__text faint">{hiddenCount} hidden · Show all</span>
          </button>
        ) : null}
        <div className="rail__spacer" />
        {item({ kind: "settings" }, SettingsIcon, "Settings")}
      </div>
      {!collapsed ? (
        <ResizeHandle side="left" onMouseDown={panel.startDrag} onStep={panel.resizeBy} label="Resize the sidebar" value={panel.displayWidth} min={76} max={360} isDragging={panel.isDragging} />
      ) : null}
    </nav>
  );
}
