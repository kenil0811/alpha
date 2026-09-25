import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Button, type ButtonVariant } from "./controls";
import { Badge, EmptyState, StatusMessage } from "./feedback";

export interface ReviewDecision {
  id: string;
  /** Button text, e.g. "Keep" or "Dismiss". */
  label: string;
  /** Past-tense label for the status message and badge, e.g. "Kept". */
  doneLabel: string;
  variant?: ButtonVariant;
}

export interface ReviewQueueProps<Item> {
  items: readonly Item[];
  getId: (item: Item) => string;
  getLabel: (item: Item) => string;
  renderItem: (item: Item) => ReactNode;
  decisions: readonly ReviewDecision[];
  /** The decision already recorded for an item (from its data), preserved across refreshes. */
  decisionOf?: (item: Item) => string | null | undefined;
  /** Saves a decision. Reject to report a failure; the item stays undecided. */
  onDecide: (item: Item, decisionId: string, reason: string) => Promise<void>;
  /** When set, a reason box is shown and passed to onDecide. */
  reasonLabel?: string;
  /** Allows one decision for every remaining undecided item, after an explicit confirmation. */
  bulk?: { decisionId: string };
  empty?: { title: string; message?: ReactNode };
}

/**
 * Decide on incoming items one at a time. Keyboard: with focus on the item card, ← and → move
 * between items and the number keys choose a decision. Decisions already made stay visible when
 * you move back; bulk decisions need a second, explicit confirmation.
 */
export function ReviewQueue<Item>({
  items,
  getId,
  getLabel,
  renderItem,
  decisions,
  decisionOf,
  onDecide,
  reasonLabel,
  bulk,
  empty,
}: ReviewQueueProps<Item>) {
  const [index, setIndex] = useState(0);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [local, setLocal] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [confirmBulk, setConfirmBulk] = useState(false);
  const card = useRef<HTMLDivElement>(null);
  const reasonId = useId();

  const decided = (item: Item): string | null => local[getId(item)] ?? decisionOf?.(item) ?? null;
  const undecided = useMemo(() => items.filter((item) => !decided(item)), [items, local, decisionOf]); // decided() reads these

  // Start at the first item that still needs a decision, once, when items first arrive.
  const positioned = useRef(false);
  useEffect(() => {
    if (positioned.current || items.length === 0) return;
    positioned.current = true;
    const first = items.findIndex((item) => !decided(item));
    if (first > 0) setIndex(first);
  }, [items]); // decided() reads current props; positioning happens only once

  useEffect(() => {
    if (index >= items.length && items.length > 0) setIndex(items.length - 1);
  }, [index, items.length]);

  if (items.length === 0) {
    // Deciding the last item can empty the list; keep the outcome of that decision visible.
    return (
      <div className="a-review">
        <EmptyState title={empty?.title ?? "Nothing to review"} message={empty?.message} />
        {message ? <StatusMessage tone={message.tone}>{message.text}</StatusMessage> : null}
      </div>
    );
  }
  const current = items[Math.min(index, items.length - 1)];
  const currentId = getId(current);
  const currentDecision = decided(current);
  const decisionLabel = (id: string | null) => decisions.find((d) => d.id === id)?.doneLabel ?? id;

  function move(delta: number) {
    setConfirmBulk(false);
    setIndex((i) => Math.max(0, Math.min(items.length - 1, i + delta)));
  }

  async function decide(decisionId: string) {
    if (saving) return;
    setSaving(true);
    setMessage(null);
    try {
      await onDecide(current, decisionId, reasons[currentId] ?? "");
      setLocal((l) => ({ ...l, [currentId]: decisionId }));
      setMessage({ tone: "success", text: `${decisionLabel(decisionId)}: ${getLabel(current)}` });
      const nextUndecided = items.findIndex((item, i) => i > index && !decided(item) && getId(item) !== currentId);
      if (nextUndecided >= 0) setIndex(nextUndecided);
    } catch (error) {
      setMessage({ tone: "danger", text: `Not saved for ${getLabel(current)}: ${error instanceof Error ? error.message : String(error)}` });
    } finally {
      setSaving(false);
      card.current?.focus();
    }
  }

  async function decideAll(decisionId: string) {
    setSaving(true);
    setConfirmBulk(false);
    let done = 0;
    const failed: string[] = [];
    for (const item of undecided) {
      try {
        await onDecide(item, decisionId, reasons[getId(item)] ?? "");
        setLocal((l) => ({ ...l, [getId(item)]: decisionId }));
        done += 1;
      } catch {
        failed.push(getLabel(item));
      }
    }
    setSaving(false);
    setMessage(
      failed.length
        ? { tone: "danger", text: `${decisionLabel(decisionId)} ${done}; not saved for ${failed.length}: ${failed.join(", ")}` }
        : { tone: "success", text: `${decisionLabel(decisionId)} ${done} items` },
    );
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.target !== card.current) return; // typing in the reason box is never a shortcut
    if (event.key === "ArrowRight") {
      event.preventDefault();
      move(1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      move(-1);
    } else {
      const digit = Number(event.key);
      if (Number.isInteger(digit) && digit >= 1 && digit <= decisions.length) {
        event.preventDefault();
        void decide(decisions[digit - 1].id);
      }
    }
  }

  const bulkDecision = bulk ? decisions.find((d) => d.id === bulk.decisionId) : undefined;
  return (
    <div className="a-review">
      <div className="a-review__nav">
        <span className="a-review__position" aria-live="polite">
          Item {Math.min(index, items.length - 1) + 1} of {items.length} · {items.length - undecided.length} decided
        </span>
        <span className="a-cluster">
          <Button small onClick={() => move(-1)} disabled={index === 0}>
            Previous
          </Button>
          <Button small onClick={() => move(1)} disabled={index >= items.length - 1}>
            Next
          </Button>
        </span>
      </div>
      <div
        ref={card}
        className="a-review__card"
        tabIndex={0}
        role="group"
        aria-roledescription="review item"
        aria-label={`${getLabel(current)}${currentDecision ? `, ${decisionLabel(currentDecision)}` : ", not decided"}`}
        onKeyDown={onKeyDown}
      >
        {currentDecision ? <Badge tone="info">{decisionLabel(currentDecision)}</Badge> : <Badge>Not decided</Badge>}
        {renderItem(current)}
        {reasonLabel ? (
          <div className="a-field">
            <label className="a-field__label" htmlFor={reasonId}>
              {reasonLabel}
            </label>
            <textarea
              id={reasonId}
              className="a-input"
              value={reasons[currentId] ?? ""}
              onChange={(event) => setReasons((r) => ({ ...r, [currentId]: event.target.value }))}
            />
          </div>
        ) : null}
        <div className="a-review__decisions">
          {decisions.map((decision, i) => (
            <Button key={decision.id} variant={decision.variant} busy={saving} busyLabel="Saving…" onClick={() => void decide(decision.id)}>
              {decision.label} <span className="a-kbd" aria-hidden="true">{i + 1}</span>
            </Button>
          ))}
        </div>
        <span className="a-field__hint">Keys: ← → to move, 1–{decisions.length} to decide (with this card focused).</span>
      </div>
      {message ? <StatusMessage tone={message.tone}>{message.text}</StatusMessage> : null}
      {bulkDecision && undecided.length > 1 ? (
        confirmBulk ? (
          <div className="a-cluster" role="group" aria-label="Confirm bulk decision">
            <span>
              {bulkDecision.label} all {undecided.length} undecided items?
            </span>
            <Button variant="danger" onClick={() => void decideAll(bulkDecision.id)} busy={saving}>
              Yes, {bulkDecision.label.toLowerCase()} {undecided.length}
            </Button>
            <Button onClick={() => setConfirmBulk(false)}>Cancel</Button>
          </div>
        ) : (
          <Button onClick={() => setConfirmBulk(true)} disabled={saving}>
            {bulkDecision.label} all {undecided.length} undecided…
          </Button>
        )
      ) : null}
    </div>
  );
}
