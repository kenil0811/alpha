/** Formatting and calendar helpers shared by kit components and compositions. Dates are ISO
 *  calendar days (YYYY-MM-DD) in the person's own timezone. */

export function formatNumber(value: number | null | undefined, options: { maximumFractionDigits?: number } = {}): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: options.maximumFractionDigits ?? 1 }).format(value);
}

export function formatWithUnit(value: number | null | undefined, unit?: string): string {
  const text = formatNumber(value);
  return unit && text !== "—" ? `${text} ${unit}` : text;
}

function toDate(day: string): Date {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1);
}

function toDay(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** Today's calendar day in this browser's timezone. */
export function today(now: Date = new Date()): string {
  return toDay(now);
}

export function addDays(day: string, days: number): string {
  const date = toDate(day);
  date.setDate(date.getDate() + days);
  return toDay(date);
}

/** "Sep 25" (or "Sep 25, 2025" outside the current year). */
export function formatDay(day: string | null | undefined): string {
  if (!day) return "—";
  const date = toDate(day.slice(0, 10));
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", ...(sameYear ? {} : { year: "numeric" }) }).format(date);
}

export interface DayPoint {
  day: string;
  /** null means no records on that day, which is different from a recorded zero. */
  value: number | null;
}

/** A continuous run of days ending on `end`, filling days without data with null. */
export function daySeries(end: string, days: number, values: ReadonlyMap<string, number | null>): DayPoint[] {
  const points: DayPoint[] = [];
  for (let i = days - 1; i >= 0; i -= 1) {
    const day = addDays(end, -i);
    const value = values.get(day);
    points.push({ day, value: value === undefined ? null : value });
  }
  return points;
}
