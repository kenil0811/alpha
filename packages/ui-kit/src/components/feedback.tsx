import type { ReactNode } from "react";
import { Button } from "./controls";
import { cx } from "./layout";

export type Tone = "info" | "success" | "warning" | "danger";

const ICON: Record<Tone, string> = { info: "i", success: "✓", warning: "!", danger: "×" };
const WORD: Record<Tone, string> = { info: "Note", success: "Done", warning: "Check", danger: "Problem" };

/** A message with an icon and a text prefix, so status never depends on color alone.
 *  Danger messages are alerts; others are polite status updates. */
export function StatusMessage({ tone = "info", children, quiet = false }: { tone?: Tone; children: ReactNode; quiet?: boolean }) {
  return (
    <div className={cx("a-status", quiet ? "a-status--quiet" : `a-status--${tone}`)} role={tone === "danger" ? "alert" : "status"}>
      {quiet ? null : (
        <span className="a-status__icon" aria-hidden="true">
          {ICON[tone]}
        </span>
      )}
      <span className="a-status__body">
        <span className="a-visually-hidden">{WORD[tone]}: </span>
        {children}
      </span>
    </div>
  );
}

export function Badge({ tone, children }: { tone?: Tone; children: ReactNode }) {
  return <span className={cx("a-badge", tone && `a-badge--${tone}`)}>{children}</span>;
}

/** What to show before there is anything: say what will appear and how to start. */
export function EmptyState({ title, message, action }: { title: string; message?: ReactNode; action?: ReactNode }) {
  return (
    <div className="a-empty" role="status">
      <p className="a-empty__title">{title}</p>
      {message ? <p className="a-empty__message">{message}</p> : null}
      {action}
    </div>
  );
}

export function LoadingState({ label = "Loading…", lines = 3 }: { label?: string; lines?: number }) {
  return (
    <div className="a-loading" role="status" aria-live="polite" aria-busy="true">
      <span className="a-visually-hidden">{label}</span>
      <div className="a-loading__lines" aria-hidden="true">
        {Array.from({ length: lines }, (_, i) => (
          <span key={i} className="a-skeleton" />
        ))}
      </div>
    </div>
  );
}

export function ErrorState({
  title = "This could not be loaded",
  message,
  onRetry,
  retryLabel = "Try again",
}: {
  title?: string;
  message?: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <div className="a-error-state" role="alert">
      <p className="a-error-state__title">{title}</p>
      {message ? <p className="a-error-state__message">{message}</p> : null}
      {onRetry ? <Button onClick={onRetry}>{retryLabel}</Button> : null}
    </div>
  );
}

export type SaveState = "idle" | "saving" | "saved" | "failed";

/** The outcome of the last save/action, announced to screen readers. A failure keeps the
 *  message and offers retry; it is never shown as saved. */
export function OperationStatus({
  state,
  error,
  savedLabel = "Saved",
  savingLabel = "Saving…",
  onRetry,
}: {
  state: SaveState;
  error?: string | null;
  savedLabel?: string;
  savingLabel?: string;
  onRetry?: () => void;
}) {
  if (state === "idle") return <div aria-live="polite" />;
  if (state === "saving") return <StatusMessage tone="info" quiet>{savingLabel}</StatusMessage>;
  if (state === "saved") return <StatusMessage tone="success">{savedLabel}</StatusMessage>;
  return (
    <StatusMessage tone="danger">
      Not saved. {error ?? "Something went wrong."}{" "}
      {onRetry ? (
        <Button small variant="ghost" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </StatusMessage>
  );
}

export interface FieldProvenance {
  source?: string;
  model?: string | null;
  previous?: { value?: unknown; source?: string } | null;
}

/** Labels a value that a model estimated, or that a person corrected. Estimates are never
 *  presented as facts. */
export function ProvenanceNote({ provenance, formatPrevious }: { provenance?: FieldProvenance | null; formatPrevious?: (value: unknown) => string }) {
  if (!provenance?.source) return null;
  if (provenance.source === "model_estimate") {
    return (
      <span className="a-provenance">
        <Badge tone="warning">Estimate</Badge>
        <span>Check and correct it if it is wrong.</span>
      </span>
    );
  }
  if (provenance.source === "user_correction") {
    const previous = provenance.previous?.value;
    return (
      <span className="a-provenance">
        <Badge tone="info">You corrected</Badge>
        {previous !== undefined && previous !== null ? (
          <span>was {formatPrevious ? formatPrevious(previous) : String(previous)}</span>
        ) : null}
      </span>
    );
  }
  return null;
}
