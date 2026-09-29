/** The appearance setting: follow the Mac, or force light or dark. Kept per window. */
import { useCallback, useEffect, useState } from "react";

export type Theme = "system" | "light" | "dark";
const KEY = "alpha.theme";

function readTheme(): Theme {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw === "system" || raw === "dark" ? raw : "light";
  } catch {
    return "light";
  }
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;
}

export function useTheme(): [Theme, (next: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>(() => (typeof window === "undefined" ? "system" : readTheme()));
  useEffect(() => applyTheme(theme), [theme]);
  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    try {
      if (next === "system") window.localStorage.removeItem(KEY);
      else window.localStorage.setItem(KEY, next);
    } catch {
      /* per-window convenience only */
    }
  }, []);
  return [theme, setTheme];
}

export function ThemeControl({ theme, onChange, compact = false }: { theme: Theme; onChange: (next: Theme) => void; compact?: boolean }) {
  const options: [Theme, string][] = compact ? [["light", "Light"], ["dark", "Dark"]] : [["system", "Match Mac"], ["light", "Light"], ["dark", "Dark"]];
  return (
    <div className="theme" role="group" aria-label="Appearance">
      {options.map(([value, label]) => (
        <button key={value} type="button" aria-pressed={theme === value || (compact && theme === "system" && value === currentSystem())} onClick={() => onChange(value)}>
          {label}
        </button>
      ))}
    </div>
  );
}

function currentSystem(): Theme {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
