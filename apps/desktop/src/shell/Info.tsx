/** Activity, Connections and Settings: trusted shell surfaces over what Core reports. */
import { useCallback, useEffect, useState, type FormEvent } from "react";
import type { BrowserSite, CapabilityEntry, CoreClient, HealthInfo, ModelConnection, SettingField } from "../core/client";
import { RunList } from "../components/RunList";
import type { RunView } from "../components/useRuns";
import { ThemeControl, type Theme } from "./theme";
import { ModelConnectionCard } from "./models";

export function Activity({ runs, error, onCancel, appNames }: { runs: RunView[]; error: string | null; onCancel: (id: string) => Promise<void>; appNames: Record<string, string> }) {
  return (
    <section className="page" aria-labelledby="activity-heading">
      <div className="modhead">
        <div className="modhead__title">
          <div>
            <h2 id="activity-heading">Activity</h2>
            <div className="faint">What ran, what it produced, what needs you</div>
          </div>
        </div>
      </div>
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
      <RunList runs={runs} onCancel={onCancel} appNames={appNames} />
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
              {s.state === "connected" ? "●" : "○"}
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
    <section className="page" aria-labelledby="connections-heading">
      <div className="modhead">
        <div className="modhead__title">
          <div>
            <h2 id="connections-heading">Connections</h2>
            <div className="faint">Accounts and services your modules may use. Alpha never shows or stores raw passwords here.</div>
          </div>
        </div>
      </div>
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
                {c.available ? "●" : "○"}
              </div>
              <div className="item__body">
                <b>{words.title}</b>
                <div className="item__sub">{c.available ? words.sub : c.unavailable_reason ?? c.arrives_with ?? "Not connected yet"}</div>
              </div>
              <span className={`pill ${c.available ? "pill--good" : "pill--gray"}`}>{c.available ? "Connected" : "Not yet"}</span>
            </div>
          );
        })}
        {items && !items.length ? <p className="empty">Nothing to connect yet.</p> : null}
      </div>
    </section>
  );
}

/** Density is a document attribute the stylesheet reads; applied at load and when changed. */
export function applyDensity(density: string): void {
  document.documentElement.dataset.density = density === "comfortable" ? "comfortable" : "compact";
}

const GROUP_WORDS: Record<string, string> = {
  Models: "Which Claude model each stage uses and how long it thinks. Changes apply to the next request or build.",
  Look: "How every module is drawn, the assistant's avatar, and rules Alpha follows when it builds or changes one.",
  "Building limits": "How a build runs, and how much it may spend before it is stopped.",
  "Signed-in browser": "How gently modules read sites through your signed-in browser.",
  Voice: "Speaking with the assistant. Dictation uses the microphone button in the assistant.",
};

/** The id a Settings section is reached by (the section links and "Open Settings -> Models"). */
export function sectionId(group: string): string {
  return `settings-${group.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

/** Every setting Core exposes, grouped, editable in place; a change is saved as it is made. */
function ConfigurableSettings({ client, onSettings }: { client: CoreClient; onSettings?: (fields: SettingField[]) => void }) {
  const [fields, setFields] = useState<SettingField[] | null>(null);
  const [note, setNote] = useState<string | null>(null);
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
      const saved = await client.updateSettings({ [field.id]: value });
      setFields(saved);
      onSettings?.(saved);
      setNote(`Saved. ${field.title} applies from the next time it is used.`);
    } catch (e) {
      setNote(`Could not save ${field.title.toLowerCase()}: ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  if (!fields?.length) return null;
  const groups = [...new Set(fields.map((f) => f.group))];
  return (
    <>
      {groups.map((group) => (
        <div key={group} className="card list" aria-label={group} id={group === "Models" ? undefined : sectionId(group)}>
          <div className="item">
            <div className="item__body">
              <b>{group}</b>
              <div className="item__sub">{GROUP_WORDS[group] ?? ""}</div>
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
      {note ? (
        <p className="panel__hint" role="status">
          {note}
        </p>
      ) : null}
    </>
  );
}

export function Settings({
  client,
  health,
  theme,
  onTheme,
  onSettings,
  section,
  connection = null,
  onRefreshConnection = () => undefined,
  onConnection = () => undefined,
}: {
  client: CoreClient;
  health: HealthInfo;
  theme: Theme;
  onTheme: (next: Theme) => void;
  /** Called with every setting after a change is saved (the shell applies look and voice). */
  onSettings?: (fields: SettingField[]) => void;
  /** A section to scroll to on open, e.g. "models". */
  section?: string;
  connection?: ModelConnection | null;
  onRefreshConnection?: () => void;
  onConnection?: (next: ModelConnection) => void;
}) {
  const [groups, setGroups] = useState<string[]>([]);
  useEffect(() => {
    client
      .getSettings()
      .then((all) => setGroups([...new Set(all.map((f) => f.group))]))
      .catch(() => undefined);
  }, [client]);
  const jump = (id: string) => document.getElementById(id)?.scrollIntoView?.({ block: "start" });
  useEffect(() => {
    if (section) jump(sectionId(section));
  }, [section, groups]);
  const sections = [...groups, "About"];
  return (
    <section className="page" aria-labelledby="settings-heading">
      <div className="modhead">
        <div className="modhead__title">
          <div>
            <h2 id="settings-heading">Settings</h2>
          </div>
        </div>
      </div>
      <nav className="settings-nav" aria-label="Settings sections">
        {sections.map((g) => (
          <button key={g} type="button" className="chip" onClick={() => jump(sectionId(g))}>
            {g}
          </button>
        ))}
      </nav>
      <ModelConnectionCard client={client} connection={connection} onRefresh={onRefreshConnection} onUpdate={onConnection} />
      <ConfigurableSettings client={client} onSettings={onSettings} />
      <div className="card list" id={sectionId("About")} aria-label="About">
        <div className="item">
          <div className="item__body">
            <b>Appearance</b>
            <div className="item__sub">Light or dark, or follow the Mac's setting.</div>
          </div>
          <ThemeControl theme={theme} onChange={onTheme} />
        </div>
        <div className="item">
          <div className="item__body">
            <b>Runs while Alpha is open</b>
            <div className="item__sub">Closing the window keeps Alpha running from the menu bar. Quit stops everything.</div>
          </div>
        </div>
        <div className="item">
          <div className="item__body">
            <b>Where your data lives</b>
            <div className="item__sub">{health.data_dir}</div>
          </div>
        </div>
        <div className="item">
          <div className="item__body">
            <b>What leaves this Mac</b>
            <div className="item__sub">
              Your requests, and what modules ask the model, go to Claude through your own Claude Code sign-in. Modules read the web only when they were made to, and sites you
              signed into only when you switch that on per module. Records, files and settings stay in the folder above.
            </div>
          </div>
        </div>
        <div className="item">
          <div className="item__body">
            <b>Keyboard shortcuts</b>
            <dl className="kv">
              <div className="kv__row">
                <dt>⌘↩</dt>
                <dd>Send a request to the assistant</dd>
              </div>
              <div className="kv__row">
                <dt>↩ / Esc</dt>
                <dd>Save or cancel a cell you are editing</dd>
              </div>
              <div className="kv__row">
                <dt>⌘W</dt>
                <dd>Close the window; Alpha keeps running</dd>
              </div>
              <div className="kv__row">
                <dt>⌘Q</dt>
                <dd>Quit Alpha and stop everything</dd>
              </div>
            </dl>
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
    </section>
  );
}
