/**
 * About you: the facts Alpha knows about the person, where each came from, and the person's
 * say over every one of them. A suggestion from a module or the assistant waits here for a
 * yes; anything can be corrected (a new fact supersedes) or forgotten.
 */
import { useCallback, useEffect, useState } from "react";
import { X } from "lucide-react";
import type { ProfileClient, ProfileFact } from "../core/client";
import { humanize } from "../modules/useModule";
import { IconButton } from "../ui/IconButton";
import { Button } from "../ui/Button";
import { InfoTip } from "../ui/InfoTip";
import "../modules/module.css";
import "../modules/views/views.css";

const SOURCE: Record<ProfileFact["provenance"], string> = {
  person: "You said so",
  module: "From a module",
  assistant: "From a conversation",
  inferred: "Alpha worked it out",
};

function shown(value: unknown): string {
  if (Array.isArray(value)) return value.map(String).join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value ?? "");
}

function parse(text: string): unknown {
  const t = text.trim();
  if (t.includes(",")) return t.split(",").map((p) => p.trim()).filter(Boolean);
  if (/^-?\d+(\.\d+)?$/.test(t)) return Number(t);
  return t;
}

export function AboutYou({ client }: { client: ProfileClient }) {
  const [facts, setFacts] = useState<ProfileFact[]>([]);
  const [suggestions, setSuggestions] = useState<ProfileFact[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [field, setField] = useState("");
  const [value, setValue] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const load = useCallback(() => {
    client
      .profile()
      .then((view) => {
        setFacts(view.facts);
        setSuggestions(view.suggestions);
        setLoaded(true);
        setError(null);
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e));
        setLoaded(true);
      });
  }, [client]);
  useEffect(load, [load]);

  async function act(work: () => Promise<unknown>) {
    try {
      await work();
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  async function add() {
    const name = field.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    if (!name || !value.trim()) return;
    await act(() => client.addFact(name, parse(value)));
    setField("");
    setValue("");
  }

  return (
    <section className="page" aria-labelledby="about-heading">
      <div className="modhead">
        <div className="modhead__title">
          <h2 id="about-heading">
            About you
            <InfoTip content="What Alpha knows and uses across your modules. Every line says where it came from; correct or forget any of it." label="About this page" />
          </h2>
        </div>
      </div>
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
      {suggestions.length ? (
        <div className="section" style={{ marginTop: 0 }}>
          <div className="section__head">
            <h2>
              Waiting for your yes
              <InfoTip content="Modules and the assistant proposed these; nothing uses them until you accept." label="About suggested facts" />
            </h2>
          </div>
          <div className="card list" aria-label="Suggested facts">
            {suggestions.map((s) => (
              <div className="item" key={s.fact_id}>
                <div className="item__body">
                  <b>
                    {humanize(s.field)}: {shown(s.value)}
                  </b>
                  <div className="item__sub">
                    {SOURCE[s.provenance]}
                    {s.source && s.source !== "person" ? ` (${s.source})` : ""}
                    {s.why ? ` · ${s.why}` : ""}
                  </div>
                </div>
                <span className="row" style={{ gap: 6 }}>
                  <button type="button" className="btn btn--sm btn--primary" onClick={() => void act(() => client.acceptFact(s.fact_id))}>
                    Yes, that's right
                  </button>
                  <button type="button" className="btn btn--sm" onClick={() => void act(() => client.rejectFact(s.fact_id))}>
                    No
                  </button>
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      <div className="section" style={{ marginTop: suggestions.length ? undefined : 0 }}>
        <div className="section__head">
          <h2>Facts</h2>
          <span className="faint">{facts.length ? `${facts.length} known` : loaded ? "Nothing yet. Add what you'd like every module to know." : "Loading…"}</span>
        </div>
        <div className="card">
          <div className="tablewrap">
            <table className="table dv-table" aria-label="Facts about you">
              <thead>
                <tr>
                  <th className="dv-gutter" />
                  <th>What</th>
                  <th>Value</th>
                  <th>Where from</th>
                  <th>Since</th>
                </tr>
              </thead>
              <tbody>
                {facts.map((f) => (
                  <tr key={f.fact_id} className="dv-row">
                    <td className="dv-gutter">
                      <IconButton aria-label={`Forget ${humanize(f.field)}`} title="Forget this" size="sm" onClick={() => void act(() => client.forgetFact(f.fact_id))}>
                        <X size={13} strokeWidth={1.75} />
                      </IconButton>
                    </td>
                    <td>{humanize(f.field)}</td>
                    <td className="editable" onClick={() => { setEditing(f.fact_id); setDraft(shown(f.value)); }} title="Click to correct">
                      {editing === f.fact_id ? (
                        <input
                          autoFocus
                          value={draft}
                          aria-label={`Correct ${humanize(f.field)}`}
                          onChange={(e) => setDraft(e.target.value)}
                          onBlur={() => { setEditing(null); if (draft.trim() && draft !== shown(f.value)) void act(() => client.addFact(f.field, parse(draft))); }}
                          onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); if (e.key === "Escape") setEditing(null); }}
                        />
                      ) : (
                        shown(f.value)
                      )}
                    </td>
                    <td className="faint">
                      {SOURCE[f.provenance]}
                      {f.source && f.source !== "person" ? ` (${f.source})` : ""}
                    </td>
                    <td className="faint">{f.recorded_at ? new Date(f.recorded_at).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : ""}</td>
                  </tr>
                ))}
                {/* A new fact, right where the rest live — no separate form card. */}
                <tr className="dv-row">
                  <td className="dv-gutter" />
                  <td>
                    <input className="dv-input" aria-label="What" value={field} onChange={(e) => setField(e.target.value)} placeholder="degree, target roles…" onKeyDown={(e) => e.key === "Enter" && void add()} />
                  </td>
                  <td>
                    <input className="dv-input" aria-label="Value" value={value} onChange={(e) => setValue(e.target.value)} placeholder="MSc Computer Science (commas make a list)" onKeyDown={(e) => e.key === "Enter" && void add()} />
                  </td>
                  <td colSpan={2}>
                    <Button size="sm" onClick={() => void add()} disabled={!field.trim() || !value.trim()}>
                      Add
                    </Button>
                  </td>
                </tr>
                {loaded && !facts.length ? (
                  <tr>
                    <td colSpan={5} className="empty" style={{ whiteSpace: "normal" }}>
                      Nothing known yet.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}
