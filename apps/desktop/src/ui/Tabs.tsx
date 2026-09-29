/** A plain, dependency-free tablist: role=tablist/tab, aria-selected, roving tabindex,
 *  Arrow/Home/End navigation. No Radix primitive exists for this in the app yet, and the
 *  behavior is ~30 lines — not worth a dependency (see StandardDropdown for the same call). */
import { useRef, type KeyboardEvent, type ReactNode } from "react";
import "./Tabs.css";

export interface TabItem {
  value: string;
  label: ReactNode;
}

export function Tabs({
  items,
  value,
  onChange,
  className,
  "aria-label": ariaLabel,
}: {
  items: TabItem[];
  value: string;
  onChange: (value: string) => void;
  /** Extra class alongside `.tabs`, for a caller that needs a different visual treatment
   *  (e.g. a segmented header control) without forking the primitive. */
  className?: string;
  "aria-label": string;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const index = items.findIndex((i) => i.value === value);
    if (index === -1) return;
    let next = -1;
    if (e.key === "ArrowRight") next = (index + 1) % items.length;
    else if (e.key === "ArrowLeft") next = (index - 1 + items.length) % items.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = items.length - 1;
    else return;
    e.preventDefault();
    const item = items[next];
    onChange(item.value);
    refs.current[item.value]?.focus();
  };

  return (
    <div role="tablist" aria-label={ariaLabel} className={className ? `tabs ${className}` : "tabs"} onKeyDown={onKeyDown}>
      {items.map((item) => {
        const selected = item.value === value;
        return (
          <button
            key={item.value}
            ref={(el) => {
              refs.current[item.value] = el;
            }}
            role="tab"
            type="button"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            className={selected ? "tabs__tab tabs__tab--current" : "tabs__tab"}
            onClick={() => onChange(item.value)}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
