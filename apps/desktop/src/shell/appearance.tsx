/** Settings -> Appearance beyond light/dark: accent colour, interface font and text size. Kept
 *  per window like the theme, applied as CSS variables on the document root. */
import { useState } from "react";

export interface Appearance {
  accent: string;
  font: string;
  size: string;
}

const KEY = "alpha.appearance";
const DEFAULTS: Appearance = { accent: "steel", font: "geist", size: "default" };

export const ACCENTS: { value: string; label: string; color: string | null }[] = [
  { value: "steel", label: "Steel", color: null }, // tokens.css default
  { value: "sage", label: "Sage", color: "#5f7a5a" },
  { value: "amber", label: "Amber", color: "#b5803f" },
  { value: "rose", label: "Rose", color: "#b05a6b" },
  { value: "plum", label: "Plum", color: "#7a5a9a" },
  { value: "graphite", label: "Graphite", color: "#4a5563" },
];

export const FONTS: { value: string; label: string; stack: string | null }[] = [
  { value: "geist", label: "Geist", stack: null },
  { value: "system", label: "San Francisco", stack: '-apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif' },
  { value: "serif", label: "Source Serif", stack: '"Source Serif 4 Variable", "Source Serif 4", Georgia, serif' },
];

export const SIZES: { value: string; label: string; px: number }[] = [
  { value: "small", label: "Small", px: 16 },
  { value: "default", label: "Default", px: 17 },
  { value: "large", label: "Large", px: 18 },
];

export function readAppearance(): Appearance {
  try {
    return { ...DEFAULTS, ...(JSON.parse(window.localStorage.getItem(KEY) ?? "{}") as Partial<Appearance>) };
  } catch {
    return DEFAULTS;
  }
}

export function applyAppearance(a: Appearance): void {
  const style = document.documentElement.style;
  const accent = ACCENTS.find((x) => x.value === a.accent)?.color;
  const font = FONTS.find((x) => x.value === a.font)?.stack;
  const size = SIZES.find((x) => x.value === a.size)?.px ?? 17;
  if (accent) style.setProperty("--primary", accent);
  else style.removeProperty("--primary");
  if (font) style.setProperty("--font-ui", font);
  else style.removeProperty("--font-ui");
  style.fontSize = size === 17 ? "" : `${size}px`;
}

export function useAppearance(): [Appearance, (change: Partial<Appearance>) => void] {
  const [appearance, setAppearance] = useState(readAppearance);
  function update(change: Partial<Appearance>) {
    const next = { ...appearance, ...change };
    setAppearance(next);
    applyAppearance(next);
    try {
      window.localStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      /* per-window convenience only */
    }
  }
  return [appearance, update];
}
