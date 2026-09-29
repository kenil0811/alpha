import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { HashRouter, useLocation, useNavigate } from "react-router";
import { Utensils, Dumbbell, Briefcase, BookOpen, CreditCard, ListChecks, Boxes, Home as HomeIcon, MessageCircle, Settings as SettingsIcon, type LucideIcon } from "lucide-react";
import type { AppSummary, CoreClient, HealthInfo } from "./core/client";
import { HttpCoreClient, isAppsClient, isWorkflowsClient } from "./core/client";
import { resolveSession } from "./core/session";
import { HANDOFF_KEY } from "./avatar/AvatarWindow";
import { useRuns } from "./components/useRuns";
import { AssistantPanel } from "./assistant/AssistantPanel";
import { Rail, surfacePath, type Surface } from "./shell/Rail";
import { Home } from "./shell/Home";
import { CommandMenu } from "./shell/CommandMenu";
import { Activity, Connections, Settings, applyDensity } from "./shell/Info";
import { ModulePage, type Section } from "./modules/ModulePage";
import { GeneratedUiFixture } from "./qualification/GeneratedUiFixture";
import { useTheme } from "./shell/theme";
import { TooltipProvider } from "./ui/Tooltip";
import { ToastProvider } from "./ui/toast";
import { CollapseToggleButton, usePanelControl } from "./ui/panel";

/** Development-only qualification fixtures: shown only in a development build opened with ?dev. */
function devTools(): boolean {
  return import.meta.env.DEV && typeof window !== "undefined" && new URLSearchParams(window.location.search).has("dev");
}

const SELECTED_KEY = "alpha.selectedConversation";
const SURFACE_KEY = "alpha.surface";

function remembered<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function remember(key: string, value: unknown): void {
  try {
    if (value === null || value === undefined) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* per-window convenience only */
  }
}

/** Parses the URL (HashRouter's `pathname`, e.g. "/m/notes-1/data") into a Surface + module
 *  section. Kept as plain parsing rather than a <Routes> tree: every destination already
 *  renders through one big switch below, so a routes tree would just duplicate that switch. */
function surfaceFromPath(pathname: string): Surface {
  const path = decodeURIComponent(pathname);
  if (path === "/activity") return { kind: "activity" };
  if (path === "/connections") return { kind: "connections" };
  if (path === "/settings") return { kind: "settings" };
  const m = path.match(/^\/m\/([^/]+)/);
  if (m) return { kind: "module", appId: m[1] };
  return { kind: "home" };
}
function sectionFromPath(pathname: string): Section | undefined {
  const m = decodeURIComponent(pathname).match(/^\/m\/[^/]+\/([^/]+)/);
  const s = m?.[1];
  return s === "app" || s === "data" || s === "activity" || s === "settings" ? s : undefined;
}
function moduleSectionPath(appId: string, section: Section): string {
  return `/m/${encodeURIComponent(appId)}/${section}`;
}

type Runtime =
  | { kind: "connecting" }
  | { kind: "connected"; client: CoreClient; health: HealthInfo }
  | { kind: "unavailable"; reason: string };

export function App(props: { client?: CoreClient; devTools?: boolean } = {}) {
  return (
    <TooltipProvider delayDuration={300}>
      <ToastProvider>
        <HashRouter>
          <AppShell {...props} />
        </HashRouter>
      </ToastProvider>
    </TooltipProvider>
  );
}

function AppShell({ client: injected, devTools: devOverride }: { client?: CoreClient; devTools?: boolean }) {
  const location = useLocation();
  const navigate = useNavigate();
  const surface = surfaceFromPath(location.pathname);
  const moduleSection = sectionFromPath(location.pathname);
  const setSurface = useCallback(
    (next: Surface) => {
      remember(SURFACE_KEY, next);
      navigate(surfacePath(next));
    },
    [navigate],
  );
  // On a fresh load (no path yet) pick up wherever the person left off; a normal navigation
  // should never fight the router, so this runs at most once.
  const restoredOnce = useRef(false);
  useEffect(() => {
    if (restoredOnce.current) return;
    restoredOnce.current = true;
    if (location.pathname === "/" || location.pathname === "") {
      const last = remembered<Surface | null>(SURFACE_KEY, null);
      if (last && last.kind !== "home") navigate(surfacePath(last), { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [runtime, setRuntime] = useState<Runtime>({ kind: "connecting" });
  // Bumped to ask the host for the runtime again: on its own every few seconds while the
  // runtime is unavailable (a first launch can wait on a macOS permission dialog), or by hand.
  const [runtimeAttempt, setRuntimeAttempt] = useState(0);
  const [conversationId, setConversationId] = useState<string | null>(() => remembered<string | null>(SELECTED_KEY, null));
  // The assistant panel is open on Home and closed on a module page unless the person opened
  // it there; both choices are remembered on this Mac.
  const [openByKind, setOpenByKind] = useState<{ home: boolean; module: boolean }>(() => readPanelState());
  const panelKind = surface.kind === "module" ? "module" : "home";
  const assistantOpen = openByKind[panelKind];
  const setAssistantOpen = useCallback(
    (open: boolean) => {
      setOpenByKind((current) => {
        const next = { ...current, [panelKind]: open };
        try {
          window.localStorage.setItem("alpha.assistant.open", JSON.stringify(next));
        } catch {
          // storage may be unavailable; the choice then lasts for this window only
        }
        return next;
      });
    },
    [panelKind],
  );

  const railPanel = usePanelControl({
    defaultWidth: 220,
    minWidth: 76,
    maxWidth: 360,
    storageKeyWidth: "alpha.rail.width",
    storageKeyCollapsed: "alpha.rail.collapsed",
    snap: true,
    snapMidpoint: 148,
  });
  const assistantPanel = usePanelControl({
    defaultWidth: 286,
    minWidth: 260,
    maxWidth: 520,
    storageKeyWidth: "alpha.assistant.width",
    storageKeyCollapsed: "alpha.assistant.collapsed",
  });
  const [isNarrow, setIsNarrow] = useState(() => (typeof window !== "undefined" ? window.innerWidth < 640 : false));
  useEffect(() => {
    const onResize = () => setIsNarrow(window.innerWidth < 640);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  const [mobileDrawer, setMobileDrawer] = useState<"modules" | null>(null);

  const [draft, setDraft] = useState<string | null>(null);
  const [modules, setModules] = useState<AppSummary[]>([]);
  const [modulesTick, setModulesTick] = useState(0);
  const dev = devOverride ?? devTools();
  const [theme, setTheme] = useTheme();
  // The person's density choice lives in Core's settings; apply it once the runtime answers.
  useEffect(() => {
    if (runtime.kind !== "connected") return;
    runtime.client
      .getSettings()
      .then((all) => {
        const density = all.find((f) => f.id === "look.density");
        if (density) applyDensity(String(density.value));
      })
      .catch(() => undefined);
  }, [runtime]);

  const selectConversation = useCallback((id: string | null) => {
    setConversationId(id);
    remember(SELECTED_KEY, id);
  }, []);
  // The desktop avatar hands over a module or a conversation through shared storage (the two
  // windows share an origin); this window goes there and comes forward.
  useEffect(() => {
    const follow = (raw: string | null) => {
      if (!raw) return;
      try {
        const handoff = JSON.parse(raw) as { app_id?: string | null; conversation_id?: string | null };
        if (handoff.conversation_id) {
          selectConversation(handoff.conversation_id);
          setSurface({ kind: "home" });
          setAssistantOpen(true);
        } else if (handoff.app_id) {
          setModulesTick((n) => n + 1);
          setSurface({ kind: "module", appId: handoff.app_id });
        }
      } catch {
        /* not a handoff */
      }
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === HANDOFF_KEY) follow(event.newValue);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [selectConversation, setSurface, setAssistantOpen]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let client = injected;
      if (!client) {
        const resolution = await resolveSession();
        if (resolution.kind === "unavailable") {
          if (!cancelled) setRuntime({ kind: "unavailable", reason: resolution.reason });
          return;
        }
        client = new HttpCoreClient(resolution.session);
      }
      try {
        const health = await client.health();
        if (!cancelled) setRuntime({ kind: "connected", client, health });
      } catch (error) {
        if (!cancelled) setRuntime({ kind: "unavailable", reason: `Runtime not reachable: ${String(error)}` });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [injected, runtimeAttempt]);
  useEffect(() => {
    if (runtime.kind !== "unavailable" || injected) return;
    const timer = setTimeout(() => setRuntimeAttempt((n) => n + 1), 5000);
    return () => clearTimeout(timer);
  }, [runtime, injected]);

  const client = runtime.kind === "connected" ? runtime.client : null;
  const nullClient = useMemo(() => new NullClient(), []);
  const { runs, error: runsError, cancel } = useRuns(client ?? nullClient);

  // The module list: reloaded when a creation finishes or a run completes (a new module shows up
  // in the rail without a restart).
  useEffect(() => {
    if (!client || !isWorkflowsClient(client)) return;
    let cancelled = false;
    client
      .listApps()
      .then((all) => {
        if (cancelled) return;
        setModules(all.filter((a) => a.state === "active" || a.origin !== "fixture"));
        if (pendingOpen.current && all.some((a) => a.app_id === pendingOpen.current)) pendingOpen.current = null;
        setModulesLoaded(true);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [client, modulesTick, runs.length]);

  const appNames = useMemo(() => Object.fromEntries(modules.map((m) => [m.app_id, m.name])), [modules]);
  // A remembered module that no longer exists (another data directory, or removed) goes back
  // to Home instead of a dead surface.
  // A module just made is opened before the list has caught up, so the fallback waits for the
  // next load to finish before judging.
  const [modulesLoaded, setModulesLoaded] = useState(false);
  const pendingOpen = useRef<string | null>(null);
  useEffect(() => {
    if (!modulesLoaded || surface.kind !== "module" || pendingOpen.current === surface.appId) return;
    if (!modules.some((m) => m.app_id === surface.appId)) setSurface({ kind: "home" });
  }, [modulesLoaded, modules, surface, setSurface]);
  const icons = useMemo(() => Object.fromEntries(modules.map((m) => [m.app_id, moduleIcon(m)])), [modules]);
  const currentModule = surface.kind === "module" ? modules.find((m) => m.app_id === surface.appId) ?? null : null;

  const openAssistant = useCallback(
    (text?: string) => {
      setAssistantOpen(true);
      setDraft(text ?? null);
    },
    [setAssistantOpen],
  );
  // "New" always means a new module: leave the module page, or the request would change it.
  const startNew = useCallback(() => {
    selectConversation(null);
    setSurface({ kind: "home" });
    openAssistant("");
  }, [openAssistant, selectConversation, setSurface]);

  // Escape steps whichever panel has focus (extended -> expanded -> collapsed); it never
  // steals Escape from an open dialog/menu, and does nothing when focus is in neither panel.
  const railRef = useRef<HTMLDivElement>(null);
  const assistRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const overlayOpen = document.querySelector('[role="dialog"], [role="menu"], [role="listbox"]') !== null;
      if (overlayOpen) return;
      const active = document.activeElement;
      if (railRef.current?.contains(active)) railPanel.handleEscape();
      else if (assistRef.current?.contains(active)) assistantPanel.handleEscape();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [railPanel, assistantPanel]);

  const assistantWidth = assistantPanel.collapsed ? 48 : assistantPanel.displayWidth;
  const railWidth = railPanel.collapsed ? 76 : railPanel.displayWidth;

  const mainContent = (
    <main className="main">
      {runtime.kind !== "connected" ? (
        <section className="page">
          <h2>Runtime</h2>
          {runtime.kind === "connecting" ? (
            <p className="panel__hint">Connecting to the local runtime…</p>
          ) : (
            <>
              <p className="notice" role="alert">
                {runtime.reason}
              </p>
              <p className="panel__hint">Alpha keeps trying on its own every few seconds.</p>
              <div className="row">
                <button type="button" className="btn btn--sm" onClick={() => setRuntimeAttempt((n) => n + 1)}>
                  Try again now
                </button>
              </div>
            </>
          )}
        </section>
      ) : surface.kind === "home" ? (
        <Home modules={modules} icons={icons} runs={runs.map((r) => r.run)} onOpen={(appId) => setSurface({ kind: "module", appId })} onNew={startNew} onActivity={() => setSurface({ kind: "activity" })} />
      ) : surface.kind === "activity" ? (
        <Activity runs={runs} error={runsError} onCancel={cancel} appNames={appNames} />
      ) : surface.kind === "connections" ? (
        <Connections client={runtime.client} />
      ) : surface.kind === "settings" ? (
        <Settings client={runtime.client} health={runtime.health} theme={theme} onTheme={setTheme} />
      ) : isWorkflowsClient(runtime.client) && isAppsClient(runtime.client) ? (
        <ModulePage
          key={`${surface.appId}:${modulesTick}`}
          client={runtime.client}
          appId={surface.appId}
          icon={icons[surface.appId]}
          onAsk={() => openAssistant()}
          runs={runs}
          onCancelRun={cancel}
          onRemoved={() => {
            setModulesTick((n) => n + 1);
            setSurface({ kind: "home" });
          }}
          section={moduleSection}
          onSectionChange={(next) => navigate(moduleSectionPath(surface.appId, next))}
        />
      ) : null}
      {dev && runtime.kind === "connected" ? (
        <section className="page">
          <GeneratedUiFixture client={runtime.client} />
        </section>
      ) : null}
    </main>
  );

  const assistantContent =
    runtime.kind === "connected" && (assistantOpen || isNarrow) && !assistantPanel.collapsed ? (
      <div ref={assistRef} id="panel-right" className={isNarrow ? "assist assist--overlay" : "assist"} style={isNarrow ? undefined : { width: assistantWidth }}>
        <AssistantPanel
          client={runtime.client}
          conversationId={conversationId}
          onSelect={selectConversation}
          onOpenApp={(appId) => {
            pendingOpen.current = appId;
            setModulesTick((n) => n + 1);
            setSurface({ kind: "module", appId });
          }}
          context={{ moduleName: currentModule?.name ?? null, appId: currentModule?.app_id ?? null }}
          headerStart={
            <CollapseToggleButton
              side="right"
              collapsed={false}
              controls="panel-right"
              onClick={() => (isNarrow ? setAssistantOpen(false) : assistantPanel.setCollapsed(true))}
            />
          }
          draft={draft}
        />
      </div>
    ) : runtime.kind === "connected" && !isNarrow ? (
      <button
        type="button"
        className="assist assist--collapsed"
        style={{ width: 48 }}
        onClick={() => {
          assistantPanel.setCollapsed(false);
          setAssistantOpen(true);
        }}
        aria-label="Open the assistant"
      >
        <MessageCircle size={18} />
      </button>
    ) : null;

  if (isNarrow) {
    return (
      <div className="app">
        {mainContent}
        {mobileDrawer === "modules" ? (
          <div className="drawer-sheet" onClick={() => setMobileDrawer(null)}>
            <div className="drawer-sheet__panel" onClick={(e) => e.stopPropagation()}>
              <Rail
                surface={surface}
                modules={modules}
                icons={icons}
                runtime={runtime.kind}
                onGo={(s) => {
                  setSurface(s);
                  setMobileDrawer(null);
                }}
                onNew={startNew}
                panel={{ ...railPanel, collapsed: false, displayWidth: 280 }}
              />
            </div>
          </div>
        ) : null}
        {assistantOpen ? assistantContent : null}
        <nav className="tabbar" aria-label="Alpha">
          <button type="button" className="tabbar__btn" aria-current={surface.kind === "home" ? "page" : undefined} onClick={() => setSurface({ kind: "home" })}>
            <HomeIcon size={18} />
            Home
          </button>
          <button type="button" className="tabbar__btn" aria-current={mobileDrawer === "modules" ? "page" : undefined} onClick={() => setMobileDrawer("modules")}>
            <Boxes size={18} />
            Modules
          </button>
          <button type="button" className="tabbar__btn" aria-current={assistantOpen ? "page" : undefined} onClick={() => setAssistantOpen(!assistantOpen)}>
            <MessageCircle size={18} />
            Assistant
          </button>
          <button type="button" className="tabbar__btn" aria-current={surface.kind === "settings" ? "page" : undefined} onClick={() => setSurface({ kind: "settings" })}>
            <SettingsIcon size={18} />
            Settings
          </button>
        </nav>
      </div>
    );
  }

  return (
    <div className="app">
      <div ref={railRef}>
        <Rail surface={surface} modules={modules} icons={icons} runtime={runtime.kind} onGo={setSurface} onNew={startNew} panel={{ ...railPanel, displayWidth: railWidth }} />
      </div>
      {mainContent}
      {assistantContent}
      {runtime.kind === "connected" ? <CommandMenu modules={modules} icons={icons} onNew={startNew} /> : null}
    </div>
  );
}

function readPanelState(): { home: boolean; module: boolean } {
  try {
    const raw = window.localStorage.getItem("alpha.assistant.open");
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<{ home: boolean; module: boolean }>;
      return { home: parsed.home ?? true, module: parsed.module ?? false };
    }
  } catch {
    // fall through to the defaults
  }
  return { home: true, module: false };
}

function moduleIcon(m: AppSummary): LucideIcon {
  const text = `${m.name} ${m.description}`.toLowerCase();
  if (/food|meal|calorie|diet|eat/.test(text)) return Utensils;
  if (/workout|gym|fitness|exercise/.test(text)) return Dumbbell;
  if (/job|opening|career|applic/.test(text)) return Briefcase;
  if (/book|read/.test(text)) return BookOpen;
  if (/money|spend|expense|budget|receipt/.test(text)) return CreditCard;
  if (/task|todo|plan/.test(text)) return ListChecks;
  return Boxes;
}

/** Stands in until the runtime connects, so hooks keep a stable client reference. */
class NullClient implements CoreClient {
  private fail(): never {
    throw new Error("runtime not connected");
  }
  health() {
    return Promise.reject(new Error("runtime not connected"));
  }
  listRuns() {
    return Promise.resolve([]);
  }
  createRun() {
    return this.fail();
  }
  run() {
    return this.fail();
  }
  cancelRun() {
    return this.fail();
  }
  events() {
    return Promise.resolve([]);
  }
  stream() {
    return new Promise<void>(() => undefined);
  }
  startConversation() {
    return this.fail();
  }
  conversation() {
    return this.fail();
  }
  listConversations() {
    return Promise.resolve([]);
  }
  appConversations() {
    return Promise.resolve([]);
  }
  getSettings() {
    return Promise.resolve([]);
  }
  browserSites() {
    return Promise.resolve({ available: false, sites: [] });
  }
  connectBrowserSite() {
    return this.fail();
  }
  removeBrowserSite() {
    return this.fail();
  }
  browserAccess() {
    return Promise.resolve([]);
  }
  setBrowserAccess() {
    return this.fail();
  }
  browserVisits() {
    return Promise.resolve([]);
  }
  updateSettings() {
    return this.fail();
  }
  replyConversation() {
    return this.fail();
  }
  retryConversation() {
    return this.fail();
  }
  cancelConversation() {
    return this.fail();
  }
  capabilities() {
    return Promise.resolve([]);
  }
}
