import { FolderPlus } from "lucide-react";
import { useEffect, useState } from "react";
import type { AppSummary, Nudge, ProfileClient } from "../core/client";
import "./pages.css";
import "../modules/module.css";

/**
 * Trial flag (AP-182): while the person decides if this is worth keeping, the blank "New
 * project" centre offers a few starter chips and real insights. Flip this to `false` to go
 * back to a fully blank centre — that's the whole revert.
 */
export const NEW_PROJECT_CENTRE_SUGGESTIONS = true;

/**
 * The blank "New project" draft: just an editable title until the person tells the Chief of
 * Staff what it's for (that's where the actual project gets made). While it's otherwise empty,
 * it can show a few starter chips built from real signals already on hand — installed modules,
 * and whatever Alpha has already noticed — never anything invented.
 */
export function NewProjectPage({
  title,
  onTitleChange,
  modules,
  client,
  onFill,
  showSuggestions = NEW_PROJECT_CENTRE_SUGGESTIONS,
}: {
  title: string;
  onTitleChange: (title: string) => void;
  modules: AppSummary[];
  /** Absent when the runtime keeps no profile; the insights strip then just stays blank. */
  client?: ProfileClient;
  /** Fills the composer with a chip's text; sending is still up to the person. */
  onFill: (text: string) => void;
  /** Defaults to the trial flag; a test can flip it independently of that module constant. */
  showSuggestions?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);
  const [nudges, setNudges] = useState<Nudge[]>([]);

  useEffect(() => {
    if (!client) return;
    let cancelled = false;
    client
      .nudges()
      .then((r) => {
        if (!cancelled) setNudges(r.nudges);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [client]);

  function save() {
    setEditing(false);
    const value = draft.trim();
    if (value) onTitleChange(value);
    else setDraft(title);
  }

  const chips = modules.slice(0, 4).map((m) => ({
    label: `File alongside ${m.name}`,
    text: `File this new project alongside ${m.name}.`,
  }));

  return (
    <section className="page" aria-labelledby="new-project-heading">
      <div className="modhead">
        <div className="modhead__title">
          <div className="modhead__ico" aria-hidden="true">
            <FolderPlus size={18} strokeWidth={1.75} />
          </div>
          {editing ? (
            <input
              autoFocus
              aria-label="Project name"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={save}
              onKeyDown={(e) => {
                if (e.key === "Enter") e.currentTarget.blur();
                if (e.key === "Escape") {
                  setDraft(title);
                  setEditing(false);
                }
              }}
            />
          ) : (
            <h2
              id="new-project-heading"
              className="editable"
              onClick={() => {
                setDraft(title);
                setEditing(true);
              }}
              title="Click to rename"
            >
              {title}
            </h2>
          )}
        </div>
      </div>

      {showSuggestions && chips.length ? (
        <div className="row" style={{ flexWrap: "wrap", gap: 8, marginTop: 24 }} aria-label="Starter options">
          {chips.map((c) => (
            <button key={c.label} type="button" className="btn btn--sm" onClick={() => onFill(c.text)}>
              {c.label}
            </button>
          ))}
        </div>
      ) : null}

      {showSuggestions && nudges.length ? (
        <div className="section">
          <div className="section__head">
            <h2>Research insights</h2>
            <span className="faint">What Alpha already noticed, in case it's relevant here.</span>
          </div>
          <div className="card list" aria-label="Research insights">
            {nudges.slice(0, 4).map((n) => (
              <div className="item" key={n.nudge_id}>
                <div className="item__body">{n.text}</div>
                <button type="button" className="btn btn--sm" onClick={() => onFill(n.next_step)}>
                  {n.next_step}
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
