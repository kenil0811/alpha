import { useId, type ReactNode } from "react";
import { formatDay, formatNumber, formatWithUnit, type DayPoint } from "../format";
import { SelectField } from "./controls";

export interface MetricCardProps {
  label: string;
  /** null shows "No data" rather than a misleading zero. */
  value: number | null;
  unit?: string;
  hint?: ReactNode;
  format?: (value: number) => string;
}

export function MetricCard({ label, value, unit, hint, format }: MetricCardProps) {
  return (
    <div className="a-metric" role="group" aria-label={label}>
      <span className="a-metric__label">{label}</span>
      <span className="a-metric__value">
        {value === null ? "No data" : format ? format(value) : formatNumber(value)}
        {value !== null && unit ? <span className="a-metric__unit">{unit}</span> : null}
      </span>
      {hint ? <span className="a-metric__hint">{hint}</span> : null}
    </div>
  );
}

export interface TrendChartProps {
  title: string;
  points: readonly DayPoint[];
  unit?: string;
  /** Controls such as a <RangeSelect>, shown beside the title. */
  controls?: ReactNode;
  height?: number;
}

/**
 * Daily values as bars. Days without any records are drawn as dashed outlines and listed as "no
 * entry", never as zero; a recorded zero is a line on the baseline. The exact numbers are
 * available as a table for screen readers and for checking.
 *
 * Bars are laid out in CSS at a fixed pixel height with fixed-size text, so a short range in a
 * wide window stays compact and readable (M1 review finding F09: the old SVG scaled its height and
 * lettering with the window width divided by the number of days).
 */
export function TrendChart({ title, points, unit, controls, height = 160 }: TrendChartProps) {
  const captionId = useId();
  const values = points.map((p) => p.value).filter((v): v is number => v !== null);
  const max = values.length ? Math.max(...values) : 0;
  const missing = points.filter((p) => p.value === null).length;
  const logged = points.length - missing;
  const total = values.reduce((sum, v) => sum + v, 0);
  const first = points[0]?.day;
  const last = points[points.length - 1]?.day;
  const summary =
    points.length === 0
      ? "No days to show."
      : `${points.length} days from ${formatDay(first)} to ${formatDay(last)}; total ${formatWithUnit(total, unit)}; highest day ${formatWithUnit(max, unit)}; ${missing} day${missing === 1 ? "" : "s"} with no entry.`;
  const plotHeight = Math.min(Math.max(height, 80), 240);

  return (
    <figure className="a-trend" aria-labelledby={captionId}>
      <div className="a-trend__header">
        <figcaption className="a-trend__caption" id={captionId}>
          {title}
        </figcaption>
        {controls}
      </div>
      {/* Few days: the plot is only as wide as its bars (at most 48px each), so the dates sit under them. */}
      <div className="a-trend__plot" role="img" aria-label={summary} style={{ height: plotHeight, maxWidth: Math.max(140, points.length * 54) }}>
        <span className="a-trend__axis a-trend__axis--max">{values.length ? formatWithUnit(max, unit) : "No entries yet"}</span>
        <div className={points.length > 14 ? "a-trend__bars a-trend__bars--dense" : "a-trend__bars"}>
          {points.map((point) => {
            const label = `${formatDay(point.day)}: ${point.value === null ? "no entry" : formatWithUnit(point.value, unit)}`;
            if (point.value === null) return <span key={point.day} className="a-trend__slot a-trend__missing" title={label} />;
            if (point.value === 0) return <span key={point.day} className="a-trend__slot a-trend__zero" title={label} />;
            const share = max > 0 ? Math.max(2, (point.value / max) * 100) : 0;
            return (
              <span key={point.day} className="a-trend__slot" title={label}>
                <span className="a-trend__bar" style={{ height: `${share}%` }} />
              </span>
            );
          })}
        </div>
        <div className="a-trend__days">
          <span className="a-trend__axis">{first ? formatDay(first) : ""}</span>
          <span className="a-trend__axis">{last && points.length > 1 ? formatDay(last) : ""}</span>
        </div>
      </div>
      <div className="a-trend__legend" aria-hidden="true">
        <span>
          <span className="a-trend__swatch a-trend__swatch--value" />
          {unit ? `Amount (${unit})` : "Amount"}
        </span>
        <span>
          <span className="a-trend__swatch a-trend__swatch--missing" />
          No entry that day
        </span>
        <span>
          Days with entries: {logged} of {points.length}
        </span>
      </div>
      <details className="a-trend__data">
        <summary>Show the numbers</summary>
        <table className="a-table">
          <caption className="a-visually-hidden">{title}</caption>
          <thead>
            <tr>
              <th scope="col">Day</th>
              <th scope="col" className="a-table__num">
                {unit ? `Amount (${unit})` : "Amount"}
              </th>
            </tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={point.day}>
                <td data-label="Day">{formatDay(point.day)}</td>
                <td data-label="Amount" className="a-table__num">
                  {point.value === null ? "No entry" : formatNumber(point.value)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

export function RangeSelect({
  value,
  onChange,
  options = [7, 14, 30],
}: {
  value: number;
  onChange: (days: number) => void;
  options?: readonly number[];
}) {
  return (
    <SelectField
      label="Period"
      value={String(value)}
      onChange={(event) => onChange(Number(event.target.value))}
      options={options.map((days) => ({ value: String(days), label: `Last ${days} days` }))}
    />
  );
}
