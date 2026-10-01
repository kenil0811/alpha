/**
 * panel.tsx — shared collapse/expand/extend/resize control for the rail and the
 * assistant panel, ported from Bridge's PanelControl (platform/apps/web/src/app/
 * components/shared/PanelControl.tsx). Plain-CSS version (this app has no Tailwind) —
 * see panel.css.
 *
 * State machine: collapsed --click/drag--> expanded --drag past default--> extended.
 * Escape steps back one level at a time (extended -> expanded -> collapsed), and only
 * acts when focus is inside this panel (or no dialog/menu is open) so it never steals
 * Escape from an open overlay.
 */
import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import { ChevronsLeft, ChevronsRight, MoveHorizontal, PanelLeftClose, PanelRightClose } from "lucide-react";
import "./panel.css";

export type PanelSide = "left" | "right";
export type PanelMode = "collapsed" | "expanded" | "extended";

function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* cosmetic preference — safe no-op */
  }
}

export interface UsePanelControlOptions {
  defaultWidth: number;
  minWidth: number;
  maxWidth: number;
  storageKeyWidth: string;
  storageKeyCollapsed: string;
  /** Legacy localStorage keys to migrate from on first read, in order. */
  migrateWidthKeys?: string[];
  migrateCollapsedKeys?: string[];
  /** Snap to collapsed/expanded on drag release instead of a continuous width (the rail). */
  snap?: boolean;
  snapMidpoint?: number;
  initialCollapsed?: boolean;
}

export interface PanelControl {
  collapsed: boolean;
  mode: PanelMode;
  width: number;
  /** Width to render while a drag is in flight (falls back to `width`). */
  displayWidth: number;
  isDragging: boolean;
  setCollapsed: (v: boolean) => void;
  toggleCollapsed: () => void;
  resizeBy: (delta: number) => void;
  startDrag: (e: MouseEvent) => void;
  /** Steps extended -> expanded -> collapsed. No-op when already collapsed. */
  handleEscape: () => boolean;
}

export function usePanelControl(opts: UsePanelControlOptions): PanelControl {
  const { defaultWidth, minWidth, maxWidth, storageKeyWidth, storageKeyCollapsed, snap, snapMidpoint, migrateWidthKeys, migrateCollapsedKeys, initialCollapsed } = opts;
  const side: PanelSide = "left"; // caller decides drag direction via startDrag's sign convention below
  void side;

  const [collapsed, setCollapsedState] = useState<boolean>(() => {
    let raw = readStored(storageKeyCollapsed);
    if (raw === null) {
      for (const legacy of migrateCollapsedKeys ?? []) {
        raw = readStored(legacy);
        if (raw !== null) break;
      }
    }
    return raw !== null ? raw === "1" : (initialCollapsed ?? false);
  });
  const [width, setWidthState] = useState<number>(() => {
    let raw = readStored(storageKeyWidth);
    if (raw === null) {
      for (const legacy of migrateWidthKeys ?? []) {
        raw = readStored(legacy);
        if (raw !== null) break;
      }
    }
    const stored = Number(raw);
    return stored >= minWidth && stored <= maxWidth ? stored : defaultWidth;
  });
  const [dragWidth, setDragWidth] = useState<number | null>(null);

  const setCollapsed = useCallback(
    (v: boolean) => {
      setCollapsedState(v);
      writeStored(storageKeyCollapsed, v ? "1" : "0");
    },
    [storageKeyCollapsed],
  );
  const setWidth = useCallback(
    (v: number) => {
      const clamped = Math.min(maxWidth, Math.max(minWidth, v));
      setWidthState(clamped);
      writeStored(storageKeyWidth, String(clamped));
    },
    [minWidth, maxWidth, storageKeyWidth],
  );
  const toggleCollapsed = useCallback(() => setCollapsed(!collapsed), [collapsed, setCollapsed]);
  const resizeBy = useCallback(
    (delta: number) => {
      setCollapsed(false);
      setWidth(width + delta);
    },
    [width, setCollapsed, setWidth],
  );

  const startDrag = useCallback(
    (e: MouseEvent) => {
      e.preventDefault();
      const startX = e.clientX;
      const startWidth = width;
      const dragSide: PanelSide = opts.snap ? "left" : "right";
      const onMove = (ev: globalThis.MouseEvent) => {
        const dx = dragSide === "left" ? ev.clientX - startX : startX - ev.clientX;
        setDragWidth(Math.min(maxWidth, Math.max(minWidth, startWidth + dx)));
      };
      const onUp = (ev: globalThis.MouseEvent) => {
        const dx = dragSide === "left" ? ev.clientX - startX : startX - ev.clientX;
        const finalWidth = Math.min(maxWidth, Math.max(minWidth, startWidth + dx));
        setDragWidth(null);
        if (snap && snapMidpoint !== undefined) {
          if (finalWidth < snapMidpoint) setCollapsed(true);
          else {
            setCollapsed(false);
            setWidth(Math.max(snapMidpoint, finalWidth));
          }
        } else {
          setWidth(finalWidth);
        }
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [width, minWidth, maxWidth, snap, snapMidpoint, defaultWidth, setCollapsed, setWidth, opts.snap],
  );

  const mode: PanelMode = collapsed ? "collapsed" : width > defaultWidth ? "extended" : "expanded";

  const handleEscape = useCallback((): boolean => {
    if (mode === "extended") {
      setWidth(defaultWidth);
      return true;
    }
    if (mode === "expanded") {
      setCollapsed(true);
      return true;
    }
    return false;
  }, [mode, defaultWidth, setWidth, setCollapsed]);

  return {
    collapsed,
    mode,
    width,
    displayWidth: dragWidth ?? width,
    isDragging: dragWidth !== null,
    setCollapsed,
    toggleCollapsed,
    resizeBy,
    startDrag,
    handleEscape,
  };
}

/**
 * useEscapeStep — wires `panel.handleEscape()` to the Escape key, only while focus is
 * within `ref` or nothing else claims to be an overlay (`data-overlay-open="true"`
 * anywhere in the document — a Radix Dialog/DropdownMenu/Popover sets this via its own
 * portal; absent that, this checks `document.querySelector('[role="dialog"]')`).
 */
export function useEscapeStep(ref: React.RefObject<HTMLElement | null>, onEscape: () => boolean): void {
  useEffect(() => {
    const handler = (e: globalThis.KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const node = ref.current;
      const focusWithin = !!node && node.contains(document.activeElement);
      const overlayOpen = document.querySelector('[role="dialog"], [role="menu"], [role="listbox"]') !== null;
      if (!focusWithin && overlayOpen) return;
      if (focusWithin || !overlayOpen) {
        if (onEscape()) e.stopPropagation();
      }
    };
    document.addEventListener("keydown", handler, true);
    return () => document.removeEventListener("keydown", handler, true);
  }, [ref, onEscape]);
}

export function CollapseToggleButton({
  side,
  collapsed,
  onClick,
  controls,
  className,
}: {
  side: PanelSide;
  collapsed: boolean;
  onClick: () => void;
  controls: string;
  className?: string;
}) {
  const Icon = collapsed ? (side === "left" ? ChevronsRight : ChevronsLeft) : side === "left" ? PanelLeftClose : PanelRightClose;
  const label = collapsed ? `Expand the ${side === "left" ? "sidebar" : "panel"}` : `Collapse the ${side === "left" ? "sidebar" : "panel"}`;
  return (
    <button type="button" className={`iconbtn panel__toggle${className ? ` ${className}` : ""}`} aria-label={label} title={label} aria-expanded={!collapsed} aria-controls={controls} onClick={onClick}>
      <Icon size={16} />
    </button>
  );
}

export function ResizeHandle({
  side,
  onMouseDown,
  onStep,
  label,
  value,
  min,
  max,
  isDragging = false,
}: {
  side: PanelSide;
  onMouseDown: (e: MouseEvent) => void;
  onStep: (delta: number) => void;
  label: string;
  value: number;
  min: number;
  max: number;
  isDragging?: boolean;
}) {
  const handleRef = useRef<HTMLDivElement>(null);
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      onStep(side === "left" ? -16 : 16);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      onStep(side === "left" ? 16 : -16);
    }
  };
  return (
    <div
      ref={handleRef}
      role="separator"
      aria-label={label}
      aria-orientation="vertical"
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={Math.round(value)}
      tabIndex={0}
      onMouseDown={onMouseDown}
      onKeyDown={onKeyDown}
      className={`panel__handle panel__handle--${side}${isDragging ? " panel__handle--dragging" : ""}`}
      title={label}
    >
      <div className="panel__handle-line" />
      <span className="panel__handle-grip" aria-hidden="true">
        <MoveHorizontal size={12} />
      </span>
    </div>
  );
}

export function CollapsedStrip({ side, onClick, children, label }: { side: PanelSide; onClick: () => void; children: ReactNode; label: string }) {
  return (
    <button type="button" className={`panel__strip panel__strip--${side}`} onClick={onClick} aria-label={label} title={label}>
      {children}
    </button>
  );
}
