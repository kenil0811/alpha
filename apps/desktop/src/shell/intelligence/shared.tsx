/** Small helpers the Intelligence sections share. */

/** A link only when the text is one plain address; anything else stays text. */
export function asLink(value: unknown): { href: string; label: string } | null {
  if (typeof value !== "string" || !/^https?:\/\/\S+$/.test(value.trim())) return null;
  try {
    return { href: value.trim(), label: new URL(value.trim()).hostname };
  } catch {
    return null;
  }
}

export function shown(value: unknown): string {
  if (Array.isArray(value)) return value.map(String).join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value ?? "");
}

