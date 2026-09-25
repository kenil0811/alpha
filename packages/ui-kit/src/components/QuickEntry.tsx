import { useId, useRef, useState, type KeyboardEvent } from "react";
import { Button } from "./controls";
import { StatusMessage } from "./feedback";
import { Form } from "./Form";
import { cx } from "./layout";

export type ParseResult<T> =
  | { status: "empty" }
  | { status: "ok"; value: T; summary: string }
  /** Saved as `summary`, but the person should see what was assumed. */
  | { status: "ambiguous"; value: T; summary: string; note: string }
  | { status: "invalid"; message: string };

export interface QuickEntryOutcome {
  /** Short description of what was stored ("3 × paper"). */
  summary?: string;
  /** Reverses the entry that was just added, if the App supports it. */
  undo?: () => Promise<void>;
}

export interface QuickEntryProps<T> {
  label: string;
  placeholder?: string;
  hint?: string;
  submitLabel?: string;
  /** Turns the typed text into the values to save; runs on every keystroke for the preview. */
  parse: (text: string) => ParseResult<T>;
  /** Saves the entry. Throw (or reject) to report a failure; the text is kept for a retry. */
  onSubmit: (value: T, text: string) => Promise<QuickEntryOutcome | void>;
  autoFocus?: boolean;
}

type Outcome =
  | { kind: "none" }
  | { kind: "saved"; summary: string; undo?: () => Promise<void> }
  | { kind: "undone"; summary: string }
  | { kind: "failed"; message: string }
  | { kind: "invalid"; message: string };

/**
 * Frequent small additions: type, see what will be saved, press Enter. Focus stays in the input
 * so the next entry can follow immediately. Failures keep the text; Escape clears it.
 */
export function QuickEntry<T>({ label, placeholder, hint, submitLabel = "Add", parse, onSubmit, autoFocus }: QuickEntryProps<T>) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [outcome, setOutcome] = useState<Outcome>({ kind: "none" });
  const parsed = parse(text);

  async function submit() {
    if (saving) return;
    const result = parse(text);
    if (result.status === "empty") {
      setOutcome({ kind: "invalid", message: "Type something to add." });
      input.current?.focus();
      return;
    }
    if (result.status === "invalid") {
      setOutcome({ kind: "invalid", message: result.message });
      input.current?.focus();
      return;
    }
    setSaving(true);
    try {
      const done = await onSubmit(result.value, text);
      setText("");
      setOutcome({ kind: "saved", summary: done?.summary ?? result.summary, undo: done?.undo });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setOutcome({ kind: "failed", message: /[.!?]$/.test(message.trim()) ? message.trim() : `${message.trim()}.` });
    } finally {
      setSaving(false);
      input.current?.focus();
    }
  }

  async function undo(summary: string, action: () => Promise<void>) {
    setSaving(true);
    try {
      await action();
      setOutcome({ kind: "undone", summary });
    } catch (error) {
      setOutcome({ kind: "failed", message: `Could not undo: ${error instanceof Error ? error.message : String(error)}` });
    } finally {
      setSaving(false);
      input.current?.focus();
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape" && !saving && text) {
      event.preventDefault();
      setText("");
      setOutcome({ kind: "none" });
    }
  }

  const previewId = `${id}-preview`;
  const hintId = hint ? `${id}-hint` : undefined;
  return (
    <Form className="a-quick-entry" onSubmit={submit}>
      <label className="a-field__label" htmlFor={id}>
        {label}
      </label>
      <div className="a-quick-entry__row">
        <input
          ref={input}
          id={id}
          className="a-input"
          value={text}
          placeholder={placeholder}
          autoFocus={autoFocus}
          autoComplete="off"
          readOnly={saving}
          aria-describedby={[previewId, hintId].filter(Boolean).join(" ")}
          aria-invalid={outcome.kind === "invalid" || undefined}
          onChange={(event) => {
            setText(event.target.value);
            if (outcome.kind === "invalid") setOutcome({ kind: "none" });
          }}
          onKeyDown={onKeyDown}
        />
        <Button type="submit" variant="primary" busy={saving} busyLabel="Saving…">
          {submitLabel}
        </Button>
      </div>
      <div
        id={previewId}
        className={cx("a-quick-entry__preview", parsed.status === "ambiguous" && "a-quick-entry__preview--ambiguous")}
      >
        {parsed.status === "ok" ? `Will add: ${parsed.summary}` : null}
        {parsed.status === "ambiguous" ? `Will add: ${parsed.summary}. ${parsed.note}` : null}
        {parsed.status === "invalid" && outcome.kind !== "invalid" ? parsed.message : null}
      </div>
      {hint ? (
        <span className="a-field__hint" id={hintId}>
          {hint}
        </span>
      ) : null}
      {outcome.kind === "saved" ? (
        <StatusMessage tone="success">
          Added {outcome.summary}.{" "}
          {outcome.undo ? (
            <Button small variant="ghost" onClick={() => void undo(outcome.summary, outcome.undo!)}>
              Undo
            </Button>
          ) : null}
        </StatusMessage>
      ) : null}
      {outcome.kind === "undone" ? <StatusMessage tone="info">Removed {outcome.summary}.</StatusMessage> : null}
      {outcome.kind === "failed" ? (
        <StatusMessage tone="danger">Not saved. {outcome.message} Your text is still there; press Enter to try again.</StatusMessage>
      ) : null}
      {outcome.kind === "invalid" ? <StatusMessage tone="danger">{outcome.message}</StatusMessage> : null}
    </Form>
  );
}
