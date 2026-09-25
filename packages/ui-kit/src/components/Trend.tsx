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
 */
export function TrendChart({ title, points, unit, controls, height = 160 }: TrendChartProps) {
  const captionId = useId();
  const barWidth = 24;
  const gap = 8;
  const top = 18;
  const bottom = 26;
  const left = 8;
  const width = left + points.length * (barWidth + gap);
  const values = points.map((p) => p.value).filter((v): v is number => v !== null);
  const max = values.length ? Math.max(...values) : 0;
  const scale = max > 0 ? (height - top - bottom) / max : 0;
  const baseline = height - bottom;
  const missing = points.filter((p) => p.value === null).length;
  const total = values.reduce((sum, v) => sum + v, 0);
  const first = points[0]?.day;
  const last = points[points.length - 1]?.day;
  const summary =
    points.length === 0
      ? "No days to show."
      : `${points.length} days from ${formatDay(first)} to ${formatDay(last)}; total ${formatWithUnit(total, unit)}; highest day ${formatWithUnit(max, unit)}; ${missing} day${missing === 1 ? "" : "s"} with no entry.`;

  return (
    <figure className="a-trend" aria-labelledby={captionId}>
      <div className="a-trend__header">
        <figcaption className="a-trend__caption" id={captionId}>
          {title}
        </figcaption>
        {controls}
      </div>
      <svg className="a-trend__svg" viewBox={`0 0 ${Math.max(width, 1)} ${height}`} role="img" aria-label={summary} preserveAspectRatio="xMinYMid meet">
        <line className="a-trend__grid" x1={0} x2={width} y1={baseline} y2={baseline} />
        <line className="a-trend__grid" x1={0} x2={width} y1={top} y2={top} />
        <text className="a-trend__axis" x={left} y={top - 6}>
          {formatWithUnit(max, unit)}
        </text>
        {points.map((point, i) => {
          const x = left + i * (barWidth + gap);
          if (point.value === null) {
            return <rect key={point.day} className="a-trend__missing" x={x + 0.5} y={top} width={barWidth - 1} height={baseline - top} rx={2} />;
          }
          if (point.value === 0) {
            return <line key={point.day} className="a-trend__zero" x1={x} x2={x + barWidth} y1={baseline - 1} y2={baseline - 1} />;
          }
          const h = Math.max(2, point.value * scale);
          return <rect key={point.day} className="a-trend__bar" x={x} y={baseline - h} width={barWidth} height={h} rx={2} />;
        })}
        {first ? (
          <text className="a-trend__axis" x={left} y={height - 8}>
            {formatDay(first)}
          </text>
        ) : null}
        {last && points.length > 1 ? (
          <text className="a-trend__axis" x={width - gap} y={height - 8} textAnchor="end">
            {formatDay(last)}
          </text>
        ) : null}
      </svg>
      <div className="a-trend__legend" aria-hidden="true">
        <span>
          <span className="a-trend__swatch a-trend__swatch--value" />
          {unit ? `Amount (${unit})` : "Amount"}
        </span>
        <span>
          <span className="a-trend__swatch a-trend__swatch--missing" />
          No entry that day
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
