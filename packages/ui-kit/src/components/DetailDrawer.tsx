import { useEffect, useId, useRef, type ReactNode } from "react";
import { Button } from "./controls";

export interface DetailDrawerProps {
  open: boolean;
  /** Called for Escape, the Close button and a click on the backdrop. */
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  /** Actions for the item (Save, a decision, Delete) and the outcome of the last one. */
  footer?: ReactNode;
}

/**
 * Inspect one item and act on it, in a native modal dialog: the rest of the page is inert,
 * focus moves into the drawer and returns to whatever opened it when it closes.
 */
export function DetailDrawer({ open, onClose, title, description, children, footer }: DetailDrawerProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const titleId = useId();

  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (open && !node.open) {
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      node.showModal();
    } else if (!open && node.open) {
      node.close();
      opener.current?.focus();
    }
  }, [open]);

  useEffect(() => () => opener.current?.focus(), []);

  return (
    <dialog
      ref={dialog}
      className="a-drawer"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === dialog.current) onClose();
      }}
    >
      {open ? (
        <div className="a-drawer__inner">
          <div className="a-drawer__header">
            <div>
              <h2 className="a-drawer__title" id={titleId}>
                {title}
              </h2>
              {description ? <div className="a-section__description">{description}</div> : null}
            </div>
            <Button variant="ghost" small onClick={onClose}>
              Close
            </Button>
          </div>
          <div className="a-drawer__body">{children}</div>
          {footer ? <div className="a-drawer__footer">{footer}</div> : null}
        </div>
      ) : null}
    </dialog>
  );
}

/** A label/value list for the fields of one item. */
export function DetailList({ items }: { items: ReadonlyArray<{ label: string; value: ReactNode }> }) {
  return (
    <dl className="a-details">
      {items.map((item) => (
        <div key={item.label} className="a-details__row">
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
