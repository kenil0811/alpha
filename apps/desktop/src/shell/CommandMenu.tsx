/** Cmd+K / Ctrl+K command menu: jump to a shell page, open an installed module, or start a new
 *  one. Built on the shared Dialog primitive; a plain substring filter and a hand-rolled listbox
 *  (Arrow/Enter/Esc) — no command-palette dependency for ~40 lines of behavior. */
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router";
import { Home, Activity, Link2, Settings, Plus, Boxes, type LucideIcon } from "lucide-react";
import type { AppSummary } from "../core/client";
import { Dialog, DialogContent, Input } from "../ui";
import { surfacePath } from "./Rail";
import "./pages.css";

interface CommandItem {
  id: string;
  label: string;
  hint?: string;
  icon: LucideIcon;
  run: () => void;
}

export function CommandMenu({
  modules,
  icons,
  onNew,
}: {
  modules: AppSummary[];
  icons: Record<string, LucideIcon>;
  onNew: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIndex(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const go = useCallback((path: string) => navigate(path), [navigate]);

  const items = useMemo<CommandItem[]>(() => {
    const nav: CommandItem[] = [
      { id: "go-home", label: "Go to Home", icon: Home, run: () => go(surfacePath({ kind: "home" })) },
      { id: "go-activity", label: "Go to Activity", icon: Activity, run: () => go(surfacePath({ kind: "activity" })) },
      { id: "go-connections", label: "Go to Connections", icon: Link2, run: () => go(surfacePath({ kind: "intelligence", tab: "connections" })) },
      { id: "go-settings", label: "Go to Settings", icon: Settings, run: () => go(surfacePath({ kind: "settings" })) },
    ];
    const openModules: CommandItem[] = modules.map((m) => ({
      id: `open-${m.app_id}`,
      label: `Open ${m.name}`,
      icon: icons[m.app_id] ?? Boxes,
      run: () => go(surfacePath({ kind: "module", appId: m.app_id })),
    }));
    const create: CommandItem = { id: "new-module", label: "New project", icon: Plus, run: onNew };
    return [...nav, ...openModules, create];
  }, [modules, icons, onNew, go]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((i) => i.label.toLowerCase().includes(q));
  }, [items, query]);

  const select = useCallback(
    (item: CommandItem | undefined) => {
      if (!item) return;
      item.run();
      setOpen(false);
    },
    [],
  );

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      select(filtered[activeIndex]);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent title="Jump to…">
        <Input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActiveIndex(0);
          }}
          onKeyDown={onKeyDown}
          placeholder="Go to a page, open a project…"
          aria-label="Command menu"
          role="combobox"
          aria-expanded={open}
          aria-controls="command-menu-list"
          aria-activedescendant={filtered[activeIndex] ? `command-menu-item-${filtered[activeIndex].id}` : undefined}
        />
        <ul id="command-menu-list" role="listbox" className="command-menu__list" aria-label="Commands">
          {filtered.length === 0 ? <li className="command-menu__empty">No matches</li> : null}
          {filtered.map((item, index) => {
            const Icon = item.icon;
            return (
              <li
                key={item.id}
                id={`command-menu-item-${item.id}`}
                role="option"
                aria-selected={index === activeIndex}
                className={index === activeIndex ? "command-menu__item command-menu__item--active" : "command-menu__item"}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => select(item)}
              >
                <Icon size={15} aria-hidden="true" />
                {item.label}
              </li>
            );
          })}
        </ul>
        <div className="command-menu__hint">
          <kbd>↑</kbd>
          <kbd>↓</kbd> to move · <kbd>Enter</kbd> to choose · <kbd>Esc</kbd> to close ·{" "}
          <kbd>⌘K</kbd> to reopen
        </div>
      </DialogContent>
    </Dialog>
  );
}
