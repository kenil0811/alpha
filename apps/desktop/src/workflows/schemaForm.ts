/**
 * Fields for an action's input form, derived from its declared input schema. This is the
 * shell's fallback for Apps without their own screen (UX §5): plain labels, the right control
 * per type, and values converted back to what the schema expects.
 */
import type { JsonSchema } from "../core/client";

export type FieldKind = "text" | "longtext" | "lines" | "number" | "integer" | "boolean" | "choice" | "json";

export interface FormField {
  name: string;
  label: string;
  hint: string | null;
  kind: FieldKind;
  required: boolean;
  choices: string[];
  /** The value the action assumes when the person leaves the field alone (schema default). */
  defaultValue: string | boolean | null;
}

function primaryType(schema: JsonSchema): string | undefined {
  if (Array.isArray(schema.type)) return schema.type.find((t) => t !== "null");
  return schema.type;
}

export function humanize(name: string): string {
  const words = name.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function formFields(schema: JsonSchema): FormField[] {
  const required = new Set(schema.required ?? []);
  return Object.entries(schema.properties ?? {}).map(([name, property]) => {
    const type = primaryType(property);
    let kind: FieldKind = "json";
    // Explicit hints first: the App's `multiline`, a long maximum, or a description that asks
    // for one entry per line. The field-name guess stays only as a last resort for older Apps.
    const perLine = /one (?:item |entry |line )?per line|one \w+ per line/i.test(property.description ?? "");
    if (property.enum?.length) kind = "choice";
    else if (type === "string")
      kind = property.multiline || perLine || (property.maxLength ?? 0) > 200 || /text|notes|lines|body/.test(name) ? "longtext" : "text";
    else if (type === "array" && primaryType(property.items ?? {}) === "string") kind = "lines";
    else if (type === "number") kind = "number";
    else if (type === "integer") kind = "integer";
    else if (type === "boolean") kind = "boolean";
    return {
      name,
      label: property.title ?? humanize(name),
      hint: property.description ?? null,
      kind,
      required: required.has(name),
      choices: (property.enum ?? []).map(String),
      defaultValue: property.default === undefined || property.default === null ? null : typeof property.default === "boolean" ? property.default : String(property.default),
    };
  });
}

export type FormValues = Record<string, string | boolean>;

/** Convert typed form values into the action's input; returns problems in plain words. */
export function toInput(fields: FormField[], values: FormValues): { input: Record<string, unknown>; problems: string[] } {
  const input: Record<string, unknown> = {};
  const problems: string[] = [];
  for (const field of fields) {
    const raw = values[field.name];
    if (field.kind === "boolean") {
      input[field.name] = Boolean(raw);
      continue;
    }
    const text = typeof raw === "string" ? raw.trim() : "";
    if (!text) {
      if (field.required) problems.push(`${field.label} is needed.`);
      continue;
    }
    if (field.kind === "lines") {
      const items = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
      if (items.length) input[field.name] = items;
      else if (field.required) problems.push(`${field.label} is needed.`);
      continue;
    }
    if (field.kind === "number" || field.kind === "integer") {
      const value = Number(text);
      if (!Number.isFinite(value) || (field.kind === "integer" && !Number.isInteger(value))) {
        problems.push(`${field.label} must be ${field.kind === "integer" ? "a whole number" : "a number"}.`);
      } else input[field.name] = value;
    } else if (field.kind === "json") {
      try {
        input[field.name] = JSON.parse(text);
      } catch {
        problems.push(`${field.label} is not in the expected form.`);
      }
    } else input[field.name] = text;
  }
  return { input, problems };
}
