import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AppSummary, CoreClient, HealthInfo } from "./core/client";
import { HttpCoreClient, isAppsClient, isWorkflowsClient } from "./core/client";
import { resolveSession } from "./core/session";
import { useRuns } from "./components/useRuns";
import { AssistantPanel } from "./assistant/AssistantPanel";
import { Rail, type Surface } from "./shell/Rail";
import { Home } from "./shell/Home";
import { Activity, Connections, Settings, applyDensity } from "./shell/Info";
import { ModulePage } from "./modules/ModulePage";
import { GeneratedUiFixture } from "./qualification/GeneratedUiFixture";
import { useTheme } from "./shell/theme";

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

type Runtime =
  | { kind: "connecting" }
  | { kind: "connected"; client: CoreClient; health: HealthInfo }
  | { kind: "unavailable"; reason: string };

export function App({ client: injected, devTools: devOverride }: { client?: CoreClient; devTools?: boolean } = {}) {
  const [runtime, setRuntime] = useState<Runtime>({ kind: "connecting" });
  const [surface, setSurfaceState] = useState<Surface>(() => remembered<Surface>(SURFACE_KEY, { kind: "home" }));
  const [conversationId, setConversationId] = useState<string | null>(() => remembered<string | null>(SELECTED_KEY, null));
  // The assistant panel is open on Home and closed on a module page unless the person opened
  // it there; both choices are remembered on this Mac. The rail can fold to icons.
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
  const [railCollapsed, setRailCollapsed] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem("alpha.rail.collapsed") === "1";
    } catch {
      return false;
    }
  });
  const toggleRail = useCallback(() => {
    setRailCollapsed((c) => {
      try {
        window.localStorage.setItem("alpha.rail.collapsed", c ? "0" : "1");
      } catch {
        // see above
      }
      return !c;
    });
  }, []);
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

  const setSurface = useCallback((next: Surface) => {
    setSurfaceState(next);
    remember(SURFACE_KEY, next);
  }, []);
  const selectConversation = useCallback((id: string | null) => {
    setConversationId(id);
    remember(SELECTED_KEY, id);
  }, []);

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
  }, [injected]);

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

  const openAssistant = useCallback((text?: string) => {
    setAssistantOpen(true);
    setDraft(text ?? null);
  }, [setAssistantOpen]);
  // "New" always means a new module: leave the module page, or the request would change it.
  const startNew = useCallback(() => {
    selectConversation(null);
    setSurface({ kind: "home" });
    openAssistant("");
  }, [openAssistant, selectConversation, setSurface]);

  return (
    <div className={`app${assistantOpen ? "" : " app--assistant-hidden"}${railCollapsed ? " app--rail-collapsed" : ""}`}>
      <Rail surface={surface} modules={modules} icons={icons} runtime={runtime.kind} onGo={setSurface} onNew={startNew} theme={theme} onTheme={setTheme} collapsed={railCollapsed} onToggleCollapsed={toggleRail} />
      <main className="main">
        {runtime.kind !== "connected" ? (
          <section className="page">
            <h2>Runtime</h2>
            {runtime.kind === "connecting" ? (
              <p className="panel__hint">Connecting to the local runtime…</p>
            ) : (
              <p className="notice" role="alert">
                {runtime.reason}
              </p>
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
          <ModulePage key={`${surface.appId}:${modulesTick}`} client={runtime.client} appId={surface.appId} icon={icons[surface.appId]} onAsk={() => openAssistant()} runs={runs} onCancelRun={cancel} />
        ) : null}
        {dev && runtime.kind === "connected" ? (
          <section className="page">
            <GeneratedUiFixture client={runtime.client} />
          </section>
        ) : null}
      </main>
      {runtime.kind === "connected" && assistantOpen ? (
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
          onHide={() => setAssistantOpen(false)}
          draft={draft}
        />
      ) : null}
      {!assistantOpen ? (
        <button type="button" className="btn btn--primary assist__fab" onClick={() => setAssistantOpen(true)}>
          Assistant
        </button>
      ) : null}
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

function moduleIcon(m: AppSummary): string {
  const text = `${m.name} ${m.description}`.toLowerCase();
  if (/food|meal|calorie|diet|eat/.test(text)) return "🍽";
  if (/workout|gym|fitness|exercise/.test(text)) return "🏋️";
  if (/job|opening|career|applic/.test(text)) return "💼";
  if (/book|read/.test(text)) return "📚";
  if (/money|spend|expense|budget|receipt/.test(text)) return "💳";
  if (/task|todo|plan/.test(text)) return "☑";
  return "▦";
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
