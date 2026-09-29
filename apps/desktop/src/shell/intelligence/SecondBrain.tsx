/** Second brain: the facts Alpha holds about the person and what each module keeps. */
import { useEffect, useState } from "react";
import { type AppSummary, type CoreClient, type ProfileFact, isProfileClient } from "../../core/client";
import { humanize } from "../../modules/useModule";
import { shown } from "./shared";

export function SecondBrain({ client, modules, icons, onOpenModule, onOpenAbout }: { client: CoreClient; modules: AppSummary[]; icons: Record<string, string>; onOpenModule: (appId: string) => void; onOpenAbout: () => void }) {
  const [facts, setFacts] = useState<ProfileFact[] | null>(null);
  const [pending, setPending] = useState(0);
  useEffect(() => {
    if (!isProfileClient(client)) {
      setFacts([]);
      return;
    }
    let cancelled = false;
    client
      .profile()
      .then((view) => {
        if (cancelled) return;
        setFacts(view.facts);
        setPending(view.suggestions.length);
      })
      .catch(() => {
        if (!cancelled) setFacts([]);
      });
    return () => {
      cancelled = true;
    };
  }, [client]);
  return (
    <div className="intel">
      <div className="card card--pad intel__card">
        <div className="intel__head">
          <b>About you</b>
          <button type="button" className="btn btn--sm" onClick={onOpenAbout}>
            {pending ? `Manage (${pending} waiting for you)` : "Manage"}
          </button>
        </div>
        {facts === null ? (
          <p className="faint">Loading…</p>
        ) : facts.length ? (
          <dl className="intel__facts" aria-label="Facts Alpha knows">
            {facts.slice(0, 12).map((f) => (
              <div key={f.fact_id}>
                <dt>{humanize(f.field)}</dt>
                <dd>{shown(f.value)}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="faint">Nothing yet. Facts arrive from your conversations and modules, and you can add them on About you.</p>
        )}
      </div>
      <div className="card card--pad intel__card">
        <div className="intel__head">
          <b>What your modules keep</b>
        </div>
        {modules.length ? (
          <ul className="intel__modules">
            {modules.map((m) => (
              <li key={m.app_id}>
                <button type="button" className="linklike" onClick={() => onOpenModule(m.app_id)}>
                  <span aria-hidden="true">{icons[m.app_id] ?? "▦"}</span> {m.name}
                </button>
                <span className="faint">{m.description}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="faint">No modules yet.</p>
        )}
      </div>
    </div>
  );
}

