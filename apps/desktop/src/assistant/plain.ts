import type { SolutionBrief } from "@alpha/contracts";

/** Everyday wording for the shell. Implementation terms stay out of the surface. */
export function deliveryLabel(delivery: "answer" | "task" | "app" | null | undefined): string {
  switch (delivery) {
    case "app":
      return "a reusable tool you can keep using";
    case "task":
      return "a one-off result";
    case "answer":
      return "an answer";
    default:
      return "";
  }
}

export const CAPABILITY_LABELS: Record<string, string> = {
  compute: "calculations on what you type",
  records: "keeping your entries and history",
  artifacts: "producing files",
  models: "estimates and classification",
  custom_ui: "its own screen",
  files: "reading your files",
  http: "reading websites and services",
  browser: "working inside websites",
  messaging: "sending messages",
  schedules: "running on a schedule",
  audio: "audio",
};

export function capabilityLabel(family: string): string {
  return CAPABILITY_LABELS[family] ?? family.replace(/_/g, " ");
}

export function fieldKindLabel(kind: string): string {
  const labels: Record<string, string> = {
    text: "text",
    number: "a number",
    boolean: "yes/no",
    date: "a date",
    datetime: "a date and time",
    choice: "one of a few choices",
    reference: "a link to another entry",
    json: "structured details",
  };
  return labels[kind] ?? kind;
}

export function briefKeeps(brief: SolutionBrief): string[] {
  return brief.data_needs.map((need) => {
    const fields = need.fields.map((f) => `${f.name.replace(/_/g, " ")} (${fieldKindLabel(f.kind)})`).join(", ");
    return `${need.collection.replace(/_/g, " ")}: ${fields}`;
  });
}
