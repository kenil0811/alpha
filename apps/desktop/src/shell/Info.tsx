/** Activity, Connections and Settings: trusted shell surfaces over what Core reports. */
import { hasTauri } from "../core/session";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { CircleCheck, Circle } from "lucide-react";
import type { BrowserSite, CapabilityEntry, CoreClient, HealthInfo, SettingField } from "../core/client";
import { RunList } from "../components/RunList";
import type { RunView } from "../components/useRuns";
import { ThemeControl, type Theme } from "./theme";
import { Badge, PageHeader, Tabs, useToast, type TabItem } from "../ui";
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

export function Connections({ client }: { client: CoreClient }) {
  const [items, setItems] = useState<CapabilityEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    client.capabilities().then(setItems).catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [client]);
  return (
    <section aria-labelledby="connections-heading">
      <PageHeader title={<span id="connections-heading">Connections</span>} />
      <div className="page--wide">
        <p className="faint" style={{ marginTop: -8, marginBottom: 16 }}>
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
              <div className="item__sub">{group === "Models" ? "Which Claude model each stage uses. Changes apply to the next request or build." : group === "Look" ? "How every module is drawn, and rules Alpha follows when it builds or changes one." : "How a build runs, and how much it may spend before it is stopped."}</div>
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

const SETTINGS_SECTIONS: TabItem[] = [
  { value: "models", label: "Models" },
  { value: "look", label: "Look & Appearance" },
  { value: "builds", label: "Builds" },
  { value: "desktop", label: "Desktop" },
  { value: "data", label: "Data & runtime" },
];

export function Settings({ client, health, theme, onTheme }: { client: CoreClient; health: HealthInfo; theme: Theme; onTheme: (next: Theme) => void }) {
  const [section, setSection] = useState("models");
  return (
    <section aria-labelledby="settings-heading">
      <PageHeader title={<span id="settings-heading">Settings</span>} />
      <div className="settings-layout">
        <nav className="settings-tabs">
          <Tabs items={SETTINGS_SECTIONS} value={section} onChange={setSection} aria-label="Settings sections" />
        </nav>
        <div className="settings-content">
          {section === "models" ? <ConfigurableSettings client={client} only={["Models"]} /> : null}
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
          ) : null}
        </div>
      </div>
    </section>
  );
}
