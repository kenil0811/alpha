import { useCallback, useRef, useState } from "react";
import { Home as HomeIcon, Settings as SettingsIcon, Boxes, MoreVertical, Sparkles, UserRound, FolderPlus, Folder, FileUp, Trash2, type LucideIcon } from "lucide-react";
import type { AppSummary, CoreClient, Project } from "../core/client";
import { isWorkflowsClient } from "../core/client";
import { Tooltip } from "../ui/Tooltip";
import { CollapseToggleButton, ResizeHandle, type PanelControl } from "../ui/panel";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator } from "../ui/DropdownMenu";
import { Dialog, DialogContent } from "../ui/Dialog";
import { useToast } from "../ui/toast";
import { moduleFilename, saveExportedModule } from "../modules/exportModule";
import { isAlphaModuleFile } from "../modules/alphaModuleAttachment";

/** Route paths the rail links to. Kept as a small helper rather than a routing dependency here,
 *  so Rail stays a plain component the App wires to react-router (it calls `navigate`/reads
 *  `pathname`, both passed in as props — no useNavigate/useLocation import needed in this file's
 *  own tests). */
const WORKSPACE_KEY = "alpha.workspace.name";

export type Surface =
  | { kind: "home" }
  | { kind: "activity" }
  | { kind: "about" }
  | { kind: "intelligence"; tab?: string }
  | { kind: "settings"; section?: string }
  | { kind: "project"; projectId: string }
  | { kind: "module"; appId: string }
  /** The blank "New project" draft: no project exists in Core yet, made only once the person
   *  answers the Chief of Staff's opening question. */
  | { kind: "newProject" };

export function surfacePath(s: Surface): string {
  switch (s.kind) {
    case "home":
      return "/";
    case "activity":
      return "/activity";
    case "about":
      return "/about";
    case "intelligence":
      return s.tab ? `/intelligence/${encodeURIComponent(s.tab)}` : "/intelligence";
    case "project":
      return `/p/${encodeURIComponent(s.projectId)}`;
    case "settings":
      return s.section ? `/settings/${encodeURIComponent(s.section)}` : "/settings";
    case "module":
      return `/m/${encodeURIComponent(s.appId)}`;
    case "newProject":
      return "/new-project";
  }
}

export function sameSurface(a: Surface, b: Surface): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === "module" && b.kind === "module") return a.appId === b.appId;
  if (a.kind === "project" && b.kind === "project") return a.projectId === b.projectId;
  return true;
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
  onNewProject,
  projects = [],
  panel,
  client,
  onModuleRemoved,
  onModuleImported,
}: {
  surface: Surface;
  modules: AppSummary[];
  /** The person's projects; a module sits under its project, the rest in the plain list. */
  projects?: Project[];
  icons: Record<string, LucideIcon>;
  runtime: "connecting" | "connected" | "unavailable";
  onGo: (surface: Surface) => void;
  /** Opens the blank "New project" draft (its centre stays blank until the person tells the
   *  Chief of Staff what it's for). Only a module-capable, session-capable runtime offers it. */
  onNewProject?: () => void;
  panel: PanelControl;
  /** Export and Delete on the module's context menu, and "Add a module from a file" need Core. */
  client?: CoreClient | null;
  onModuleRemoved?: (appId: string) => void;
  onModuleImported?: (appId: string) => void;
}) {
  const collapsed = panel.collapsed;
  const { visible, hiddenCount, reorder, hide, showAll } = useModuleOrdering(modules);
  const dragId = useRef<string | null>(null);
  const toast = useToast();
  const [deleting, setDeleting] = useState<AppSummary | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const importInputRef = useRef<HTMLInputElement>(null);
  // Controlled so a right-click can open the same menu the ⋯ button does.
  const [openMenuFor, setOpenMenuFor] = useState<string | null>(null);

  const exportModuleFile = useCallback(
    async (m: AppSummary) => {
      if (!client || !isWorkflowsClient(client)) return;
      try {
        const blob = await client.exportModule(m.app_id);
        const { savedTo } = await saveExportedModule(moduleFilename(m.app_id), blob);
        toast.show(savedTo ? "Saved to Downloads" : `Exported ${m.name}`);
      } catch (e) {
        toast.show(e instanceof Error ? e.message : `Couldn't export ${m.name}`);
      }
    },
    [client, toast],
  );

  const confirmDelete = useCallback(async () => {
    if (!deleting || !client || !isWorkflowsClient(client)) return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await client.removeApp(deleting.app_id, null);
      onModuleRemoved?.(deleting.app_id);
      setDeleting(null);
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Couldn't remove this module.");
    } finally {
      setDeleteBusy(false);
    }
  }, [client, deleting, onModuleRemoved]);

  const importFile = useCallback(
    async (file: File) => {
      if (!client || !isWorkflowsClient(client)) return;
      try {
        const result = await client.importModuleFile(file);
        onModuleImported?.(result.app_id);
        toast.show(`Added ${result.name}`);
      } catch (e) {
        toast.show(e instanceof Error ? e.message : "Couldn't add that module.");
      }
    },
    [client, onModuleImported, toast],
  );

  const filed = new Set(projects.flatMap((p) => p.modules));
  const byId = new Map(modules.map((m) => [m.app_id, m]));
  const unfiled = visible.filter((m) => !filed.has(m.app_id));
  const item = (target: Surface, Icon: LucideIcon, label: string) => (
    <button
      key={target.kind === "module" ? `module:${target.appId}` : target.kind === "project" ? `project:${target.projectId}` : target.kind}
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
        onContextMenu={(e) => {
          e.preventDefault();
          // Right-click opens the same menu the ⋯ button does — one menu to keep in sync,
          // driven by the same open/closed state rather than two separate ones.
          setOpenMenuFor(m.app_id);
        }}
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
          <DropdownMenu open={openMenuFor === m.app_id} onOpenChange={(open) => setOpenMenuFor(open ? m.app_id : null)}>
            <DropdownMenuTrigger asChild>
              <button type="button" className="iconbtn iconbtn--sm navrow__menu" aria-label={`${m.name} options`}>
                <MoreVertical size={14} />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem onSelect={() => onGo(target)}>Open</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => hide(m.app_id)}>Hide from sidebar</DropdownMenuItem>
              {client && isWorkflowsClient(client) ? (
                <DropdownMenuItem onSelect={() => void exportModuleFile(m)}>
                  <FileUp size={14} strokeWidth={1.75} aria-hidden="true" /> Export…
                </DropdownMenuItem>
              ) : null}
              {client && isWorkflowsClient(client) ? (
                <DropdownMenuItem
                  className="ui-menu__item--danger"
                  onSelect={() => {
                    setDeleteError(null);
                    setDeleting(m);
                  }}
                >
                  <Trash2 size={14} strokeWidth={1.75} aria-hidden="true" /> Delete
                </DropdownMenuItem>
              ) : null}
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
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button type="button" className="brand__name" aria-label={`Workspace: ${workspace}. Profile and workspace`}>
                {workspace}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem onSelect={() => onGo({ kind: "about" })}>
                <UserRound size={14} strokeWidth={1.75} aria-hidden="true" /> About you
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setRenaming(true)}>Rename workspace</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => onGo({ kind: "settings" })}>
                <SettingsIcon size={14} strokeWidth={1.75} aria-hidden="true" /> Settings
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
        <CollapseToggleButton side="left" collapsed={collapsed} onClick={panel.toggleCollapsed} controls="rail-body" className="rail__fold" />
      </div>
      <div id="rail-body" className="rail__body">
        {item({ kind: "home" }, HomeIcon, "Home")}
        {projects.map((p) => (
          <div key={p.project_id} className="rail__project">
            {item({ kind: "project", projectId: p.project_id }, Folder, p.name)}
            <div className="rail__nested">
              {p.modules.map((appId) => {
                const m = byId.get(appId);
                return m ? moduleRow(m) : null;
              })}
            </div>
          </div>
        ))}
        {unfiled.map(moduleRow)}
        <input
          ref={importInputRef}
          type="file"
          accept=".alphamodule"
          className="sr-only"
          aria-hidden="true"
          tabIndex={-1}
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) void importFile(file);
          }}
        />
        {onNewProject ? (
          <button type="button" className="navbtn navbtn--new" onClick={onNewProject} aria-label="New project" title={collapsed ? "New project" : undefined}>
            <span className="navbtn__ico" aria-hidden="true" style={{ color: "var(--primary)" }}>
              <FolderPlus size={16} strokeWidth={1.75} />
            </span>
            <span className="navbtn__text">{collapsed ? "New" : "New project"}</span>
          </button>
        ) : null}
        {client && isWorkflowsClient(client) ? (
          // "Add a module from a file" used to hang off the old "New" (new module) button;
          // module creation itself now only happens by asking the Chief of Staff, so this is
          // the one thing left that needs its own entry point.
          <button
            type="button"
            className="navbtn navbtn--quiet"
            aria-label="Import a module…"
            title={collapsed ? "Import a module…" : undefined}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const file = Array.from(e.dataTransfer.files).find(isAlphaModuleFile);
              if (file) void importFile(file);
            }}
            onClick={() => importInputRef.current?.click()}
          >
            <span className="navbtn__ico" aria-hidden="true">
              <FileUp size={16} strokeWidth={1.75} />
            </span>
            <span className="navbtn__text">{collapsed ? "Import" : "Import a module…"}</span>
          </button>
        ) : null}
        {!collapsed && hiddenCount > 0 ? (
          <button type="button" className="navbtn navbtn--hidden" onClick={showAll}>
            <span className="navbtn__text faint">{hiddenCount} hidden · Show all</span>
          </button>
        ) : null}
        <div className="rail__spacer" />
        {item({ kind: "intelligence" }, Sparkles, "Intelligence")}
        {item({ kind: "settings" }, SettingsIcon, "Settings")}
      </div>
      {!collapsed ? (
        <ResizeHandle side="left" onMouseDown={panel.startDrag} onStep={panel.resizeBy} label="Resize the sidebar" value={panel.displayWidth} min={76} max={360} isDragging={panel.isDragging} />
      ) : null}
      <Dialog open={deleting !== null} onOpenChange={(open) => !open && setDeleting(null)}>
        {deleting ? (
          <DialogContent title={`Delete ${deleting.name}?`}>
            <p className="panel__hint">Deletes the module, its records, run history, and assistant notes. This cannot be undone.</p>
            {deleteError ? (
              <p className="notice" role="alert">
                {deleteError}
              </p>
            ) : null}
            <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
              <button type="button" className="btn btn--sm" disabled={deleteBusy} onClick={() => setDeleting(null)}>
                Cancel
              </button>
              <button type="button" className="btn btn--sm btn--danger" disabled={deleteBusy} onClick={() => void confirmDelete()}>
                Delete
              </button>
            </div>
          </DialogContent>
        ) : null}
      </Dialog>
    </nav>
  );
}
