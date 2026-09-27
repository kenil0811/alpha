/** Activity, Connections and Settings: trusted shell surfaces over what Core reports. */
import { useEffect, useState } from "react";
import type { CapabilityEntry, CoreClient, HealthInfo, SettingField } from "../core/client";
import { RunList } from "../components/RunList";
import type { RunView } from "../components/useRuns";
import { ThemeControl, type Theme } from "./theme";

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
  browser: { title: "A browser", sub: "Sites that need clicking and typing" },
  schedules: { title: "Schedules", sub: "Running on a timer while Alpha is open" },
};

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

/** Every setting Core exposes, grouped, editable in place; a change is saved as it is made. */
function ConfigurableSettings({ client }: { client: CoreClient }) {
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
    setFields((all) => (all ?? []).map((f) => (f.id === field.id ? { ...f, value } : f)));
    try {
      setFields(await client.updateSettings({ [field.id]: value }));
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
        <div key={group} className="card list" aria-label={group}>
          <div className="item">
            <div className="item__body">
              <b>{group}</b>
              <div className="item__sub">{group === "Models" ? "Which Claude model each stage uses. Changes apply to the next request or build." : "How much a build may spend before it is stopped."}</div>
            </div>
          </div>
          {fields
            .filter((f) => f.group === group)
            .map((f) => (
              <div key={f.id} className="item">
                <div className="item__body">
                  <label htmlFor={`setting-${f.id}`}>
                    <b>{f.title}</b>
                  </label>
                  <div className="item__sub">{f.description}</div>
                </div>
                {f.kind === "choice" ? (
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

export function Settings({ client, health, theme, onTheme }: { client: CoreClient; health: HealthInfo; theme: Theme; onTheme: (next: Theme) => void }) {
  return (
    <section className="page" aria-labelledby="settings-heading">
      <div className="modhead">
        <div className="modhead__title">
          <div>
            <h2 id="settings-heading">Settings</h2>
          </div>
        </div>
      </div>
      <ConfigurableSettings client={client} />
      <div className="card list">
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
