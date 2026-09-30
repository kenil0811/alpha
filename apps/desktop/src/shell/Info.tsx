/** Activity, Connections and Settings: trusted shell surfaces over what Core reports. */
import { hasTauri } from "../core/session";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { CircleCheck, Circle, Cpu, HardDrive, Hammer, MoreVertical, Monitor, Palette, Settings as SettingsIcon, type LucideIcon } from "lucide-react";
import { isModelAccountsClient, isWorkflowsClient, type BrowserSite, type CapabilityEntry, type CoreClient, type HealthInfo, type ModelProviderAccount, type SettingField, type WorkflowsClient } from "../core/client";
import { RunList } from "../components/RunList";
import type { RunView } from "../components/useRuns";
import { ThemeControl, type Theme } from "./theme";
import { keycodeFor, labelFor, readShortcut, shortcutLabel, writeShortcut, type PttShortcut } from "./ptt";
import { setSpeakEnabled, speakEnabled } from "./tts";
import { readTranscriptionMode, writeTranscriptionMode, type TranscriptionMode } from "./voice";
import { Badge, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, IconButton, PageHeader, useToast } from "../ui";
import "./pages.css";

export function Activity({ runs, error, onCancel, appNames }: { runs: RunView[]; error: string | null; onCancel: (id: string) => Promise<void>; appNames: Record<string, string> }) {
  return (
    <section aria-labelledby="activity-heading">
      <PageHeader title={<span id="activity-heading">Activity</span>} />
      <div className="page--wide">
        <p className="faint" style={{ marginTop: -8, marginBottom: 16 }}>
          What ran, what it produced, what needs you
        </p>
        {error ? (
          <p className="notice" role="alert">
            {error}
          </p>
        ) : null}
        <RunList runs={runs} onCancel={onCancel} appNames={appNames} />
      </div>
    </section>
  );
}

const FAMILY_WORDS: Record<string, { title: string; sub: string }> = {
  records: { title: "Saved data", sub: "Tables your modules keep on this Mac" },
  artifacts: { title: "Files", sub: "Files your modules produce" },
  models: { title: "Claude (your subscription)", sub: "Builds modules and answers questions inside them" },
  web: { title: "The web", sub: "Fetching pages and searching" },
  browser: { title: "A browser Alpha keeps", sub: "Pages drawn by scripts, and sites you sign into below" },
  schedules: { title: "Schedules", sub: "Running on a timer while Alpha is open" },
};

/** Sites the person signs into in Alpha's own browser window; modules read through them only
 *  when switched on per module. */
function SignedInSites({ client }: { client: CoreClient }) {
  const [available, setAvailable] = useState(true);
  const [sites, setSites] = useState<BrowserSite[]>([]);
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const load = useCallback(() => {
    client
      .browserSites()
      .then((page) => {
        setAvailable(page.available);
        setSites(page.sites);
      })
      .catch(() => undefined);
  }, [client]);
  useEffect(load, [load]);
  useEffect(() => {
    if (!sites.some((s) => s.state === "signing_in")) return;
    const timer = window.setInterval(load, 2000);
    return () => window.clearInterval(timer);
  }, [sites, load]);
  async function connect(e: FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    try {
      await client.connectBrowserSite(draft.trim());
      setNote("A browser window has opened. Sign in there as you normally would, then close it.");
      setDraft("");
      load();
    } catch (err) {
      setNote(err instanceof Error ? err.message : String(err));
    }
  }
  async function remove(site: string) {
    await client.removeBrowserSite(site).catch(() => undefined);
    load();
  }
  const STATE: Record<BrowserSite["state"], string> = { signing_in: "Waiting for you to sign in and close the window", connected: "Signed in", not_connected: "Not signed in" };
  return (
    <div className="section">
      <div className="section__head">
        <h2>Sites you are signed into</h2>
        <span className="faint">Alpha opens the site in its own browser window; you sign in; Alpha never sees the password. A module reads through that session only when you switch it on in the module's Settings.</span>
      </div>
      <div className="card list" aria-label="Signed-in sites">
        {sites.map((s) => (
          <div className="item" key={s.site}>
            <div className="item__ico" aria-hidden="true">
              {s.state === "connected" ? <CircleCheck size={16} /> : <Circle size={16} />}
            </div>
            <div className="item__body">
              <b>{s.site}</b>
              <div className="item__sub">
                {STATE[s.state]}
                {s.last_error ? ` · ${s.last_error}` : ""}
                {s.apps.length ? ` · used by ${s.apps.length} module${s.apps.length === 1 ? "" : "s"}` : ""}
              </div>
            </div>
            {s.state !== "connected" && s.state !== "signing_in" ? (
              <button type="button" className="btn btn--sm" onClick={() => void client.connectBrowserSite(s.site).then(load)}>
                Sign in again
              </button>
            ) : null}
            <button type="button" className="btn btn--sm btn--ghost" onClick={() => void remove(s.site)} aria-label={`Remove ${s.site}`}>
              Remove
            </button>
          </div>
        ))}
        <form className="item" onSubmit={connect} aria-label="Sign in to a site">
          <div className="item__body">
            <label htmlFor="new-site">
              <b>Sign in to a site</b>
            </label>
            <div className="item__sub">Type the site's name, for example linkedin.com or indeed.com. Sign in with the site's own email and password: sign-ins that go through Google or Apple do not complete in this window, because those services refuse a browser that another program opened.</div>
          </div>
          <input id="new-site" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="linkedin.com" style={{ width: 200 }} disabled={!available} />
          <button type="submit" className="btn btn--primary btn--sm" disabled={!available || !draft.trim()}>
            Sign in…
          </button>
        </form>
      </div>
      {!available ? <p className="panel__hint">The browser is not set up on this Mac (Node or the browser worker is missing).</p> : null}
      {note ? (
        <p className="panel__hint" role="status">
          {note}
        </p>
      ) : null}
    </div>
  );
}

export function Connections({ client, embedded = false }: { client: CoreClient; embedded?: boolean }) {
  const [items, setItems] = useState<CapabilityEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    client.capabilities().then(setItems).catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [client]);
  return (
    <section aria-labelledby="connections-heading">
      {embedded ? (
        <h3 id="connections-heading" className="settings-section__title">Connections</h3>
      ) : (
        <PageHeader title={<span id="connections-heading">Connections</span>} />
      )}
      <div className={embedded ? undefined : "page--wide"}>
        <p className="faint" style={{ marginTop: embedded ? 0 : -8, marginBottom: 16 }}>
          Accounts and services your modules may use. Alpha never shows or stores raw passwords here.
        </p>
        {error ? (
          <p className="notice" role="alert">
            {error}
          </p>
        ) : null}
        <SignedInSites client={client} />
        <div className="card list">
          {(items ?? []).map((c) => {
            const words = FAMILY_WORDS[c.family] ?? { title: c.family, sub: c.description };
            return (
              <div className="item" key={c.family}>
                <div className="item__ico" aria-hidden="true">
                  {c.available ? <CircleCheck size={16} /> : <Circle size={16} />}
                </div>
                <div className="item__body">
                  <b>{words.title}</b>
                  <div className="item__sub">{c.available ? words.sub : c.unavailable_reason ?? c.arrives_with ?? "Not connected yet"}</div>
                </div>
                <Badge variant={c.available ? "success" : "neutral"}>{c.available ? "Connected" : "Not yet"}</Badge>
              </div>
            );
          })}
          {items && !items.length ? <p className="empty">Nothing to connect yet.</p> : null}
        </div>
      </div>
    </section>
  );
}

/** Density is a document attribute the stylesheet reads; applied at load and when changed. */
export function applyDensity(density: string): void {
  document.documentElement.dataset.density = density === "comfortable" ? "comfortable" : "compact";
}

const PROVIDER_STATE_LABEL: Record<ModelProviderAccount["state"], string> = {
  connected: "Connected",
  needs_sign_in: "Not signed in",
  needs_key: "Needs a key",
  cli_missing: "Not installed on this Mac",
  key_saved: "Key saved",
  not_configured: "Not connected",
};

const PROVIDER_SIGN_IN_HINT: Record<string, string> = {
  claude: "Run `claude` in a terminal, then choose /login and sign in with your Anthropic Console account.",
  chatgpt: "Run `codex` in a terminal, then `codex login`, and sign in with ChatGPT — or add an API key instead.",
};

/** Claude (Console account by default), ChatGPT, OpenRouter and Grok: sign-in state and keys,
 *  which live only in the macOS Keychain — never shown here once saved, only their last 4
 *  characters. The model id each key-based provider uses, and Claude's console/API-key choice,
 *  are the "Models" settings just below this card. */
function ProviderAccounts({ client }: { client: CoreClient }) {
  const [providers, setProviders] = useState<ModelProviderAccount[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const toast = useToast();

  const load = useCallback(() => {
    if (!isModelAccountsClient(client)) return;
    client.listModelAccounts().then(setProviders).catch(() => setProviders([]));
  }, [client]);
  useEffect(load, [load]);

  if (!isModelAccountsClient(client) || !providers) return null;

  async function save(id: string, label: string) {
    const key = (drafts[id] ?? "").trim();
    if (!key || !isModelAccountsClient(client)) return;
    setBusy(id);
    try {
      const updated = await client.saveModelKey(id, key);
      setProviders((all) => (all ?? []).map((p) => (p.id === id ? updated : p)));
      setDrafts((d) => ({ ...d, [id]: "" }));
      toast.show(`${label}: key saved.`);
    } catch (e) {
      toast.show(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function remove(id: string, label: string) {
    if (!isModelAccountsClient(client)) return;
    setBusy(id);
    try {
      const updated = await client.removeModelKey(id);
      setProviders((all) => (all ?? []).map((p) => (p.id === id ? updated : p)));
      toast.show(`${label}: key removed.`);
    } catch (e) {
      toast.show(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function reconnect(id: string, label: string) {
    if (!isModelAccountsClient(client)) return;
    setBusy(id);
    try {
      const updated = await client.reconnectModelAccount(id);
      setProviders((all) => (all ?? []).map((p) => (p.id === id ? updated : p)));
      setNotes((n) => ({ ...n, [id]: updated.dot.tooltip }));
      toast.show(`${label}: reconnecting…`);
    } catch (e) {
      toast.show(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="card list" aria-label="Model providers">
      {providers.map((p) => {
        const showKeyField = p.id !== "claude" || p.state === "needs_key" || p.state === "key_saved";
        return (
          <div className="item item--stack" key={p.id}>
            <div className="item__body">
              <span className="row" style={{ gap: 8, alignItems: "center" }}>
                <span
                  aria-label={p.dot.tooltip}
                  title={p.dot.tooltip}
                  style={{
                    display: "inline-block",
                    width: 9,
                    height: 9,
                    borderRadius: "50%",
                    background: p.dot.color === "green" ? "var(--status-ok, #22c55e)" : p.dot.color === "red" ? "var(--status-error, #ef4444)" : "var(--status-off, #9ca3af)",
                    flexShrink: 0,
                  }}
                />
                <b>{p.label}</b>
                {p.id === "claude" ? <Badge variant="neutral">Default</Badge> : null}
              </span>
              <div className="item__sub">
                {PROVIDER_STATE_LABEL[p.state]}
                {p.key_last4 ? ` · saved key ending •••• ${p.key_last4}` : ""}
              </div>
              {(p.state === "needs_sign_in" || p.state === "cli_missing") && PROVIDER_SIGN_IN_HINT[p.id] ? (
                <div className="item__sub">{PROVIDER_SIGN_IN_HINT[p.id]}</div>
              ) : null}
              {notes[p.id] ? (
                <div className="item__sub" role="status">
                  {notes[p.id]}
                </div>
              ) : null}
            </div>
            <div className="stack" style={{ gap: 6, alignItems: "flex-end" }}>
              {showKeyField ? (
                <span className="row" style={{ gap: 6 }}>
                  <input
                    type="password"
                    placeholder={p.key_last4 ? `•••• ${p.key_last4}` : "Paste a key"}
                    value={drafts[p.id] ?? ""}
                    onChange={(e) => setDrafts((d) => ({ ...d, [p.id]: e.target.value }))}
                    style={{ width: 160 }}
                  />
                  <button type="button" className="btn btn--sm" disabled={busy === p.id || !(drafts[p.id] ?? "").trim()} onClick={() => void save(p.id, p.label)}>
                    Save
                  </button>
                  {p.key_last4 ? (
                    <button type="button" className="btn btn--sm btn--ghost" disabled={busy === p.id} onClick={() => void remove(p.id, p.label)}>
                      Remove
                    </button>
                  ) : null}
                </span>
              ) : null}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <IconButton aria-label={`${p.label} options`} size="sm" disabled={busy === p.id}>
                    <MoreVertical size={14} aria-hidden="true" />
                  </IconButton>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onSelect={() => void reconnect(p.id, p.label)}>Reconnect</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Every setting Core exposes, grouped, editable in place; a change is saved as it is made.
 *  `only`, when given, renders just those groups (the section a Settings tab owns); omitted
 *  renders every group Core reports, for a section that hasn't reserved specific group names. */
function ConfigurableSettings({ client, only, exclude }: { client: CoreClient; only?: string[]; exclude?: string[] }) {
  const [fields, setFields] = useState<SettingField[] | null>(null);
  const toast = useToast();
  useEffect(() => {
    let cancelled = false;
    client
      .getSettings()
      .then((all) => {
        if (!cancelled) setFields(all);
      })
      .catch(() => {
        if (!cancelled) setFields([]);
      });
    return () => {
      cancelled = true;
    };
  }, [client]);
  async function change(field: SettingField, raw: string) {
    const value = field.kind === "integer" ? Number(raw) : raw;
    if (field.kind === "integer" && !Number.isInteger(value)) return;
    if (field.id === "look.density") applyDensity(String(value));
    setFields((all) => (all ?? []).map((f) => (f.id === field.id ? { ...f, value } : f)));
    try {
      setFields(await client.updateSettings({ [field.id]: value }));
      toast.show(`Saved. ${field.title} applies from the next time it is used.`);
    } catch (e) {
      toast.show(`Could not save ${field.title.toLowerCase()}: ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  if (!fields?.length) return null;
  const groups = [...new Set(fields.map((f) => f.group))].filter((g) => (!only || only.includes(g)) && !exclude?.includes(g));
  if (!groups.length) return null;
  return (
    <>
      {groups.map((group) => (
        <div key={group} className="card list" aria-label={group}>
          <div className="item">
            <div className="item__body">
              <b>{group}</b>
              <div className="item__sub">{group === "Models" ? "Which provider Alpha uses, and which Claude model each stage uses. Changes apply to the next request or build." : group === "Look" ? "How every module is drawn, and rules Alpha follows when it builds or changes one." : "How a build runs, and how much it may spend before it is stopped."}</div>
            </div>
          </div>
          {fields
            .filter((f) => f.group === group)
            .map((f) => (
              <div key={f.id} className={f.kind === "text" ? "item item--stack" : "item"}>
                <div className="item__body">
                  <label htmlFor={`setting-${f.id}`}>
                    <b>{f.title}</b>
                  </label>
                  <div className="item__sub">{f.description}</div>
                </div>
                {f.kind === "text" ? (
                  <div className="stack" style={{ gap: 6, width: "100%" }}>
                    <textarea key={String(f.value ?? "")} id={`setting-${f.id}`} defaultValue={String(f.value ?? "")} rows={10} maxLength={f.maximum ?? undefined} onBlur={(e) => e.target.value !== String(f.value ?? "") && void change(f, e.target.value)} />
                    {String(f.value ?? "") !== String(f.default ?? "") ? (
                      <div className="row">
                        <button type="button" className="btn btn--sm" onClick={() => void change(f, String(f.default ?? ""))}>
                          Reset to Alpha's defaults
                        </button>
                      </div>
                    ) : (
                      <span className="faint">These are Alpha's defaults. Edit them freely; you can always reset.</span>
                    )}
                  </div>
                ) : f.kind === "choice" ? (
                  <select id={`setting-${f.id}`} className="btn btn--sm" value={String(f.value)} onChange={(e) => void change(f, e.target.value)}>
                    {f.options.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className="row" style={{ gap: 6, alignItems: "center" }}>
                    <input id={`setting-${f.id}`} type="number" min={f.minimum ?? undefined} max={f.maximum ?? undefined} value={String(f.value)} onChange={(e) => void change(f, e.target.value)} style={{ width: 88 }} />
                    {f.unit ? <span className="faint">{f.unit}</span> : null}
                  </span>
                )}
              </div>
            ))}
        </div>
      ))}
    </>
  );
}

/** The desktop assistant window: on or off, remembered by the host. Only inside the Mac app. */
function AvatarSetting() {
  const [shown, setShown] = useState<boolean | null>(null);
  useEffect(() => {
    if (!hasTauri()) return;
    let cancelled = false;
    import("@tauri-apps/api/core")
      .then(({ invoke }) => invoke<boolean>("avatar_is_visible"))
      .then((visible) => {
        if (!cancelled) setShown(visible);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  if (shown === null) return null;
  const set = async (visible: boolean) => {
    setShown(visible);
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      setShown(await invoke<boolean>("avatar_visible", { visible }));
    } catch {
      setShown(!visible);
    }
  };
  return (
    <div className="card list" aria-label="Desktop assistant">
      <div className="item">
        <div className="item__body">
          <b>Alpha on your desktop</b>
          <div className="item__sub">A small Alpha stays above your other windows. Click it or speak to log something, ask a question, open a module or start something new.</div>
        </div>
        <div className="toggle" role="group" aria-label="Desktop assistant">
          <button type="button" aria-pressed={shown} onClick={() => void set(true)}>
            Shown
          </button>
          <button type="button" aria-pressed={!shown} onClick={() => void set(false)}>
            Hidden
          </button>
        </div>
      </div>
    </div>
  );
}

/** Modules that were only taken out of use (before removal deleted things) can go for good. */
function RemovedModules({ client }: { client: WorkflowsClient }) {
  const [items, setItems] = useState<{ app_id: string; name: string }[]>([]);
  const [state, setState] = useState<"idle" | "ask" | "busy" | string>("idle");
  const load = useCallback(() => {
    client
      .removedModules()
      .then(setItems)
      .catch(() => setItems([]));
  }, [client]);
  useEffect(load, [load]);
  if (!items.length && state === "idle") return null;
  return (
    <div className="card list" style={{ marginBottom: 14 }} aria-label="Removed modules">
      <div className="item">
        <div className="item__body">
          <b>Removed modules still on this Mac</b>
          <div className="item__sub">
            {items.length ? `${items.map((m) => m.name).join(", ")}. ` : ""}
            {items.length ? "They were taken out of use earlier; their records, history and what was said about them are still stored. Deleting cannot be undone." : state}
          </div>
        </div>
        {items.length ? (
          state === "ask" ? (
            <span className="row" style={{ gap: 6 }}>
              <button
                type="button"
                className="btn btn--sm btn--danger"
                onClick={() => {
                  setState("busy");
                  client
                    .deleteRemovedModules()
                    .then((n) => {
                      setState(`Deleted ${n} module${n === 1 ? "" : "s"} and everything about ${n === 1 ? "it" : "them"}.`);
                      load();
                    })
                    .catch((e: unknown) => setState(e instanceof Error ? e.message : String(e)));
                }}
              >
                Delete for good
              </button>
              <button type="button" className="btn btn--sm" onClick={() => setState("idle")}>
                Cancel
              </button>
            </span>
          ) : (
            <button type="button" className="btn btn--sm" disabled={state === "busy"} onClick={() => setState("ask")}>
              {state === "busy" ? "Deleting…" : `Delete ${items.length}`}
            </button>
          )
        ) : null}
      </div>
    </div>
  );
}

/** Hold a key to speak to Alpha instead of typing. Fn by default (a hardware modifier flag, so
 *  it is watched natively — see `src-tauri/src/ptt.rs`); recording another key/combination goes
 *  through the same native watcher. Web-only preview has no host to watch anything, so it says so. */
/** Whether the Chief of Staff says its replies aloud (native macOS speech, or the browser's on
 *  the web preview). On by default; the person can turn it off from either place. */
function SpeakRepliesSetting() {
  const [on, setOn] = useState(() => speakEnabled());
  const set = (next: boolean) => {
    setSpeakEnabled(next);
    setOn(next);
  };
  return (
    <div className="card list" aria-label="Speak replies">
      <div className="item">
        <div className="item__body">
          <b>Speak replies</b>
          <div className="item__sub">Alpha says its replies aloud, in the desktop assistant.</div>
        </div>
        <div className="toggle" role="group" aria-label="Speak replies">
          <button type="button" aria-pressed={on} onClick={() => set(true)}>
            On
          </button>
          <button type="button" aria-pressed={!on} onClick={() => set(false)}>
            Off
          </button>
        </div>
      </div>
    </div>
  );
}

function PushToTalkSetting() {
  const [shortcut, setShortcut] = useState<PttShortcut>(() => readShortcut());
  const [recording, setRecording] = useState(false);
  const [permission, setPermission] = useState<boolean | null>(null);

  useEffect(() => {
    if (!hasTauri()) return;
    let cancelled = false;
    import("@tauri-apps/api/core")
      .then(({ invoke }) => invoke<boolean>("ptt_permission"))
      .then((granted) => {
        if (!cancelled) setPermission(granted);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!recording) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setRecording(false);
        return;
      }
      const code = keycodeFor(e.code);
      if (code === null) return; // a bare modifier (or unmapped key): keep waiting
      e.preventDefault();
      const next: PttShortcut = { mode: "key", code, shift: e.shiftKey, control: e.ctrlKey, alt: e.altKey, command: e.metaKey, label: labelFor(e.code) };
      writeShortcut(next);
      setShortcut(next);
      setRecording(false);
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [recording]);

  const chooseFn = () => {
    const next: PttShortcut = { mode: "fn" };
    writeShortcut(next);
    setShortcut(next);
    setRecording(false);
  };

  const grantAccess = async () => {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("ptt_request_permission");
      setPermission(await invoke<boolean>("ptt_permission"));
    } catch {
      /* not inside Tauri, or the command isn't there yet */
    }
  };

  return (
    <div className="card list" aria-label="Push to talk">
      <div className="item">
        <div className="item__body">
          <b>Push to talk</b>
          {hasTauri() ? (
            <>
              <div className="item__sub">Hold this key anywhere to speak to Alpha instead of typing. Release to stop.</div>
              {permission === false ? (
                <div className="item__sub">
                  Alpha needs Input Monitoring permission to notice the key while another app is focused.{" "}
                  <button type="button" className="btn btn--sm" onClick={() => void grantAccess()}>
                    Grant access
                  </button>
                </div>
              ) : null}
            </>
          ) : (
            <div className="item__sub">Desktop app only.</div>
          )}
        </div>
        {hasTauri() ? (
          <div className="row" style={{ gap: 6 }}>
            <button type="button" className={shortcut.mode === "fn" ? "btn btn--sm btn--primary" : "btn btn--sm"} aria-pressed={shortcut.mode === "fn"} onClick={chooseFn}>
              Fn (default)
            </button>
            <button type="button" className={shortcut.mode === "key" ? "btn btn--sm btn--primary" : "btn btn--sm"} aria-pressed={shortcut.mode === "key"} onClick={() => setRecording(true)}>
              {recording ? "Press a key…" : shortcut.mode === "key" ? shortcutLabel(shortcut) : "Record a key…"}
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

const TRANSCRIPTION_OPTIONS: { value: TranscriptionMode; label: string }[] = [
  { value: "automatic", label: "Automatic" },
  { value: "native", label: "On this Mac" },
  { value: "groq", label: "Groq Whisper" },
  { value: "openai", label: "OpenAI" },
];

/** Which speech-to-text a mic recording uses: cloud (Groq/OpenAI, needs a key in Settings ->
 *  Models) or this Mac's own recognition. Compact by design: the choice's effect is one line,
 *  in the (i) tooltip, not a paragraph under the field. */
function TranscriptionSetting() {
  const [mode, setMode] = useState<TranscriptionMode>(() => readTranscriptionMode());
  return (
    <div className="card list" aria-label="Transcription">
      <div className="item">
        <div className="item__body">
          <span className="row" style={{ gap: 6, alignItems: "center" }}>
            <b>Transcription</b>
            <span title="Automatic uses Groq or OpenAI when a key is saved in Settings -> Models, otherwise this Mac's own speech recognition.">ⓘ</span>
          </span>
        </div>
        <select
          aria-label="Transcription"
          className="btn btn--sm"
          value={mode}
          onChange={(e) => {
            const next = e.target.value as TranscriptionMode;
            writeTranscriptionMode(next);
            setMode(next);
          }}
        >
          {TRANSCRIPTION_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

const SETTINGS_SECTIONS: { value: string; label: string; icon: LucideIcon }[] = [
  { value: "models", label: "Models", icon: Cpu },
  { value: "look", label: "Look & Appearance", icon: Palette },
  { value: "builds", label: "Builds", icon: Hammer },
  { value: "desktop", label: "Desktop", icon: Monitor },
  { value: "data", label: "Data & runtime", icon: HardDrive },
];

export function Settings({
  client,
  health,
  theme,
  onTheme,
  section: requested,
  onSection,
}: {
  client: CoreClient;
  health: HealthInfo;
  theme: Theme;
  onTheme: (next: Theme) => void;
  section?: string;
  onSection?: (section: string) => void;
}) {
  const [own, setOwn] = useState("models");
  const section = requested && SETTINGS_SECTIONS.some((s) => s.value === requested) ? requested : onSection ? "models" : own;
  const setSection = onSection ?? setOwn;
  return (
    <section aria-labelledby="settings-heading" className="settings">
      <header className="settings__head">
        <span className="settings__headico" aria-hidden="true">
          <SettingsIcon size={16} />
        </span>
        <div>
          <h2 id="settings-heading">Settings</h2>
          <p>How Alpha works on this Mac</p>
        </div>
      </header>
      <div className="settings-layout">
        <nav className="settings-nav" aria-label="Settings sections">
          {SETTINGS_SECTIONS.map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              type="button"
              className={value === section ? "settings-nav__item settings-nav__item--current" : "settings-nav__item"}
              aria-current={value === section ? "page" : undefined}
              onClick={() => setSection(value)}
            >
              <Icon size={16} aria-hidden="true" />
              {label}
              {value === section ? <span className="settings-nav__dot" aria-hidden="true" /> : null}
            </button>
          ))}
        </nav>
        <div className="settings-content">
          {section === "models" ? (
            <>
              <ProviderAccounts client={client} />
              <ConfigurableSettings client={client} only={["Models"]} />
            </>
          ) : null}
          {section === "look" ? (
            <>
              <ConfigurableSettings client={client} only={["Look"]} />
              <div className="card list">
                <div className="item">
                  <div className="item__body">
                    <b>Appearance</b>
                    <div className="item__sub">Light or dark, or follow the Mac's setting.</div>
                  </div>
                  <ThemeControl theme={theme} onChange={onTheme} />
                </div>
              </div>
            </>
          ) : null}
          {section === "builds" ? <ConfigurableSettings client={client} exclude={["Models", "Look"]} /> : null}
          {section === "desktop" ? (
            <>
              <AvatarSetting />
              <SpeakRepliesSetting />
              <PushToTalkSetting />
              <TranscriptionSetting />
              <div className="card list">
                <div className="item">
                  <div className="item__body">
                    <b>Runs while Alpha is open</b>
                    <div className="item__sub">Closing the window keeps Alpha running from the menu bar. Quit stops everything.</div>
                  </div>
                </div>
              </div>
            </>
          ) : null}
          {section === "data" ? (
            <>
            {isWorkflowsClient(client) ? <RemovedModules client={client} /> : null}
            <div className="card list">
              <div className="item">
                <div className="item__body">
                  <b>Where your data lives</b>
                  <div className="item__sub">{health.data_dir}</div>
                </div>
              </div>
              <div className="item">
                <div className="item__body">
                  <b>Runtime</b>
                  <div className="item__sub">
                    Core {health.core_version} · Python {health.python_version.split(" ")[0]} · internal development build
                  </div>
                </div>
              </div>
            </div>
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}
