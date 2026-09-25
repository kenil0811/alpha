import { useRef, useState, type FormEvent } from "react";
import type { SyntheticRunRequest } from "../core/client";

const MODES: { value: NonNullable<SyntheticRunRequest["mode"]>; label: string }[] = [
  { value: "succeed", label: "Complete normally" },
  { value: "fail", label: "Fail inside the worker" },
  { value: "hang", label: "Hang (cancel to stop)" },
  { value: "crash", label: "Crash without output" },
];

export function RequestPanel({ onSubmit }: { onSubmit: (request: SyntheticRunRequest) => Promise<void> }) {
  const [text, setText] = useState("");
  const [mode, setMode] = useState<NonNullable<SyntheticRunRequest["mode"]>>("succeed");
  const [busy, setBusy] = useState(false);
  const textArea = useRef<HTMLTextAreaElement>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      await onSubmit({ text, mode, spawn_child: true });
      setText("");
    } finally {
      setBusy(false);
      // Quick entry: the next request starts where the last one did.
      textArea.current?.focus();
    }
  }

  return (
    <section className="panel" aria-labelledby="request-heading">
      <h2 id="request-heading">Request</h2>
      <p className="panel__hint">
        Development fixture: the text is sent through a supervised worker process and its result comes
        back below. This proves the runtime path; it does not create a workflow yet.
      </p>
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="request-text">Text to send</label>
          <textarea
            id="request-text"
            ref={textArea}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Type anything…"
            autoFocus
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") e.currentTarget.form?.requestSubmit();
            }}
          />
        </div>
        <div className="row" style={{ marginTop: "var(--space-3)" }}>
          <div className="field">
            <label htmlFor="request-mode">Worker behavior</label>
            <select id="request-mode" value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}>
              {MODES.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          <button type="submit" className="button button--primary" disabled={busy} style={{ alignSelf: "flex-end" }}>
            {busy ? "Starting…" : "Run"}
          </button>
        </div>
      </form>
    </section>
  );
}
