/**
 * One place that knows what a field kind looks like and how typed text becomes a value, for
 * every derived page, table cell and form in the shell.
 */
import { formatDay, formatNumber, humanize } from "./useModule";

export interface FieldInfo {
  name: string;
  kind: string;
  required?: boolean;
  description?: string;
  choices?: string[] | null;
  done_choices?: string[] | null;
}

export const NUMERIC_KINDS = new Set(["number", "integer"]);
export const TEXT_KINDS = new Set(["text", "long_text", "url"]);
export const CHOICE_KINDS = new Set(["choice", "status", "multiselect"]);
export const DATE_KINDS = new Set(["date", "datetime"]);

export function isNumeric(kind: string): boolean {
  return NUMERIC_KINDS.has(kind);
}

/** The value as words for a cell: numbers with units, days short, choices as pills. */
export function showValue(value: unknown, kind: string, unit?: string | null): string {
  if (value === null || value === undefined || value === "") return "";
  if (isNumeric(kind)) return typeof value === "number" ? formatNumber(value, unit) : String(value);
  if (kind === "date") return formatDay(String(value));
  if (kind === "datetime") return new Date(String(value)).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  if (kind === "boolean") return value ? "Yes" : "No";
  if (kind === "multiselect") return Array.isArray(value) ? value.map((v) => humanize(String(v))).join(", ") : String(value);
  if (kind === "choice" || kind === "status") return humanize(String(value));
  if (kind === "url") return String(value).replace(/^https?:\/\//, "").slice(0, 48);
  return String(value);
}

/** Typed text back into a stored value. Empty text clears the field. */
export function coerce(text: string, kind: string): unknown {
  if (isNumeric(kind)) {
    if (text.trim() === "") return null;
    const n = Number(text);
    return Number.isFinite(n) ? n : text;
  }
  if (kind === "boolean") return text === "true";
  if (kind === "multiselect") {
    const parts = text
      .split(",")
      .map((p) => p.trim())
      .filter(Boolean);
    return parts.length ? parts : null;
  }
  return text === "" ? null : text;
}

export function inputType(kind: string): string {
  if (isNumeric(kind)) return "number";
  if (kind === "date") return "date";
  if (kind === "datetime") return "datetime-local";
  if (kind === "url") return "url";
  return "text";
}

/** The text a cell editor starts with. */
export function editText(value: unknown, kind: string): string {
  if (value === null || value === undefined) return "";
  if (kind === "multiselect" && Array.isArray(value)) return value.join(", ");
  if (kind === "boolean") return value ? "true" : "false";
  return String(value);
}

/** The field that names a record: declared, else the first text field, else the first field. */
export function titleFieldOf(fields: FieldInfo[], declared?: string | null): string | undefined {
  if (declared && fields.some((f) => f.name === declared)) return declared;
  return (fields.find((f) => f.kind === "text") ?? fields[0])?.name;
}

export function firstOfKind(fields: FieldInfo[], kinds: Set<string>): FieldInfo | undefined {
  return fields.find((f) => kinds.has(f.kind));
}

/** A status field's open choices: everything that does not mean finished. */
export function openChoices(field: FieldInfo): string[] {
  const done = new Set(field.done_choices ?? []);
  return (field.choices ?? []).filter((c) => !done.has(c));
}
