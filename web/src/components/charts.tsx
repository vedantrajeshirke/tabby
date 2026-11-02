import { Fragment, useEffect, useRef, useState } from "react";
import type { Dashboard } from "../api";
import { formatMoney } from "../format";

/** Bars grow from a square baseline to a 4px rounded end. */
function Bar({ share, className }: { share: number; className: string }) {
  if (share <= 0) return null;
  return <div className={`h-2.5 rounded-r ${className}`} style={{ width: `${Math.max(share * 100, 1)}%` }} />;
}

export function CategorySplit({ rows }: { rows: Dashboard["categories"]["rows"] }) {
  const largest = rows[0]?.total ?? 1;
  return (
    <ul className="space-y-4">
      {rows.map((row, index) => (
        <li key={row.category}>
          <div className="flex items-baseline justify-between gap-4 text-sm">
            <span className="min-w-0 font-medium text-pine">
              {row.category}
              {index === 0 && rows.length > 1 && <span className="ml-2 text-xs font-normal text-muted">Biggest</span>}
            </span>
            <span className="amount shrink-0 whitespace-nowrap">
              <span className="font-semibold">{formatMoney(row.total)}</span>
              <span className="ml-2 inline-block w-10 text-right text-xs text-muted">{Math.round(row.share * 100)}%</span>
            </span>
          </div>
          <div className="mt-1.5">
            <Bar share={row.total / largest} className={index === 0 && rows.length > 1 ? "bg-expense" : "bg-ink"} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function changeText(row: NonNullable<Dashboard["comparison"]>["rows"][number]) {
  if (row.change === 0) return "No change";
  const sign = row.change > 0 ? "+" : "−";
  const ratio = row.change_ratio === null ? "new" : `${sign}${Math.abs(Math.round(row.change_ratio * 100))}%`;
  return `${sign}${formatMoney(Math.abs(row.change))} (${ratio})`;
}

export function PeriodComparison({ comparison }: { comparison: NonNullable<Dashboard["comparison"]> }) {
  const largest = Math.max(...comparison.rows.map((row) => Math.max(row.current, row.previous)), 1);
  return (
    <>
      <div className="flex gap-4 text-xs text-muted">
        <span className="flex items-center gap-1.5"><span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm bg-ink" />This period</span>
        <span className="flex items-center gap-1.5"><span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm bg-previous" />Last period</span>
      </div>
      <table className="mt-3 w-full text-sm">
        <thead className="sr-only">
          <tr>
            <th scope="col">Category</th>
            <th scope="col">Amounts</th>
            <th scope="col">Change</th>
          </tr>
        </thead>
        <tbody>
          {comparison.rows.map((row) => (
            <Fragment key={row.category}>
            <tr className="border-t border-line">
              <td className="py-3 pr-3 align-top font-medium text-pine sm:w-44">{row.category}</td>
              <td className="hidden w-full py-3 pr-4 align-top sm:table-cell">
                <div aria-hidden="true" className="space-y-0.5">
                  <Bar share={row.current / largest} className="bg-ink" />
                  <Bar share={row.previous / largest} className="bg-previous" />
                </div>
              </td>
              <td className="amount py-3 text-right align-top whitespace-nowrap">
                <span className="font-semibold">{formatMoney(row.current)}</span>
                <span className="text-muted"> vs {formatMoney(row.previous)}</span>
                <span className={`mt-0.5 block text-xs ${row.change > 0 ? "text-expense" : row.change < 0 ? "text-forest" : "text-muted"}`}>
                  {changeText(row)}
                </span>
              </td>
            </tr>
            <tr aria-hidden="true" className="sm:hidden">
              <td colSpan={3} className="pb-3">
                <div className="space-y-0.5">
                  <Bar share={row.current / largest} className="bg-ink" />
                  <Bar share={row.previous / largest} className="bg-previous" />
                </div>
              </td>
            </tr>
            </Fragment>
          ))}
        </tbody>
      </table>
    </>
  );
}

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** A clean top for the axis: 1, 2 or 5 times a power of ten, at or above the largest value. */
function niceMax(value: number) {
  if (value <= 0) return 100;
  const power = 10 ** Math.floor(Math.log10(value));
  return ([1, 2, 5, 10].find((step) => step * power >= value) ?? 10) * power;
}

const HEIGHT = 200;
const PAD = { top: 16, right: 16, bottom: 26, left: 48 };

export function SpendingTrend({ points }: { points: Dashboard["trend"]["points"] }) {
  const [ref, width] = useWidth();
  const [active, setActive] = useState<number | null>(null);
  const top = niceMax(Math.max(...points.map((point) => point.total)));
  const innerWidth = Math.max(width - PAD.left - PAD.right, 1);
  const innerHeight = HEIGHT - PAD.top - PAD.bottom;
  const xAt = (i: number) => PAD.left + (points.length === 1 ? innerWidth / 2 : (i / (points.length - 1)) * innerWidth);
  const yAt = (value: number) => PAD.top + innerHeight - (value / top) * innerHeight;
  const slot = points.length === 1 ? innerWidth : innerWidth / (points.length - 1);
  const shown = active === null ? null : points[active];
  const last = points.length - 1;
  const inProgress = points[last]?.in_progress;
  const settled = inProgress ? points.slice(0, last) : points;
  const path = (list: typeof points, offset = 0) => list.map((p, i) => `${i ? "L" : "M"}${xAt(i + offset)} ${yAt(p.total)}`).join(" ");

  return (
    <div ref={ref} className="relative" onMouseLeave={() => setActive(null)}>
      {width > 0 && (
        <svg width={width} height={HEIGHT} role="img" aria-label="Total spending by period. The same numbers are in the table below.">
          {[0, 0.5, 1].map((step) => (
            <g key={step}>
              <line x1={PAD.left} x2={width - PAD.right} y1={yAt(top * step)} y2={yAt(top * step)} stroke="var(--color-line)" />
              <text x={PAD.left - 8} y={yAt(top * step) + 4} textAnchor="end" fontSize="11" fill="var(--color-muted)" className="amount">
                ${(top * step).toLocaleString()}
              </text>
            </g>
          ))}
          <path d={path(settled)} fill="none" stroke="var(--color-ink)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
          {inProgress && last > 0 && (
            <path d={path(points.slice(last - 1), last - 1)} fill="none" stroke="var(--color-ink)" strokeWidth="2" strokeLinecap="round" strokeDasharray="1 5" />
          )}
          {points.map((point, i) => (
            <g key={point.full_label}>
              <circle cx={xAt(i)} cy={yAt(point.total)} r={active === i ? 6 : 4} fill={i === last && inProgress ? "var(--color-expense)" : "var(--color-ink)"} stroke="#fff" strokeWidth="2" />
              <text x={xAt(i)} y={HEIGHT - 8} textAnchor="middle" fontSize="11" fill="var(--color-muted)">{point.label}</text>
              <rect
                x={xAt(i) - slot / 2}
                y={0}
                width={slot}
                height={HEIGHT}
                fill="transparent"
                tabIndex={0}
                aria-label={`${point.full_label}: ${formatMoney(point.total)}`}
                onMouseEnter={() => setActive(i)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
                onClick={() => setActive(i)}
              />
            </g>
          ))}
        </svg>
      )}
      {shown && active !== null && (
        <div
          role="status"
          className="pointer-events-none absolute z-10 -translate-x-1/2 rounded-lg bg-pine px-2.5 py-1.5 text-xs whitespace-nowrap text-white shadow"
          style={{ left: Math.min(Math.max(xAt(active), 64), width - 64), top: Math.max(yAt(shown.total) - 48, 0) }}
        >
          <p className="text-white/75">{shown.full_label}{shown.in_progress ? " (so far)" : ""}</p>
          <p className="amount font-semibold">{formatMoney(shown.total)}</p>
        </div>
      )}
      <p className="mt-1 text-xs text-muted">
        {inProgress && last > 0 ? "The dotted line and red dot mark the current period, which isn't finished." : ""}
        {points.length === 1 ? "Your trend builds up as you add expenses from more periods." : ""}
      </p>
      <details className="mt-2 text-xs">
        <summary className="cursor-pointer font-medium text-forest">View as table</summary>
        <table className="mt-2 w-full">
          <tbody>
            {points.map((point) => (
              <tr key={point.full_label} className="border-t border-line">
                <th scope="row" className="py-1.5 text-left font-normal text-muted">{point.full_label}{point.in_progress ? " (so far)" : ""}</th>
                <td className="amount py-1.5 text-right font-medium">{formatMoney(point.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
