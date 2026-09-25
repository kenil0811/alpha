import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../styles/tokens.css"), "utf8");

function tokens(block: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const match of block.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) out[match[1]] = match[2].toLowerCase();
  return out;
}

const light = tokens(css.slice(0, css.indexOf("@media (prefers-color-scheme: dark)")));
const dark = { ...light, ...tokens(css.slice(css.indexOf("@media (prefers-color-scheme: dark)"))) };

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// WCAG 2.2 AA: 4.5:1 for text, 3:1 for component boundaries, focus indicators and chart marks.
const TEXT: Array<[string, string]> = [
  ["color-text", "color-bg"],
  ["color-text", "color-surface"],
  ["color-text", "color-surface-muted"],
  ["color-text-muted", "color-bg"],
  ["color-text-muted", "color-surface"],
  ["color-accent", "color-surface"],
  ["color-accent-contrast", "color-accent"],
  ["color-danger", "color-surface"],
  ["color-warning", "color-surface"],
  ["color-success", "color-surface"],
  ["color-text", "color-danger-bg"],
  ["color-text", "color-warning-bg"],
  ["color-text", "color-success-bg"],
  ["color-text", "color-info-bg"],
];
const NON_TEXT: Array<[string, string]> = [
  ["color-border-strong", "color-surface"],
  ["color-focus", "color-surface"],
  ["color-focus", "color-bg"],
  ["chart-1", "color-surface"],
  ["chart-missing", "color-surface"],
];

describe.each([
  ["light", light],
  ["dark", dark],
])("%s theme tokens", (_name, theme) => {
  it.each(TEXT)("%s on %s meets 4.5:1", (fg, bg) => {
    expect(theme[fg], fg).toBeDefined();
    expect(contrast(theme[fg], theme[bg])).toBeGreaterThanOrEqual(4.5);
  });
  it.each(NON_TEXT)("%s against %s meets 3:1", (fg, bg) => {
    expect(contrast(theme[fg], theme[bg])).toBeGreaterThanOrEqual(3);
  });
});
