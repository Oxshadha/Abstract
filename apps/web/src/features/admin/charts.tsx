import { Link } from "@tanstack/react-router";
import { TriangleAlert } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { shortDate } from "./format";

/**
 * Hand-written SVG charts for the admin Overview (spec 018, D97). Monochrome by construction:
 * greys from the chart tokens, told apart by shade, pattern and label, never by colour alone.
 * Every chart has a summary for its accessible name and a data table for screen readers (AC8).
 */

const GREYS = ["var(--color-chart-1)", "var(--color-chart-3)", "var(--color-chart-2)", "var(--color-chart-4)", "var(--color-chart-5)"];

export interface Series {
  key: string;
  label: string;
  values: number[];
}

function useWidth(fallback: number) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => { if (entry && entry.contentRect.width > 0) setWidth(entry.contentRect.width); });
    ro.observe(el);
    return () => { ro.disconnect(); };
  }, []);
  return { ref, width };
}

/** A round top for the axis: 0.37 -> 0.4, 1234 -> 1500. */
function niceMax(value: number): number {
  if (value <= 0) return 1;
  const exp = Math.pow(10, Math.floor(Math.log10(value)));
  const n = value / exp;
  const step = n <= 1 ? 1 : n <= 1.5 ? 1.5 : n <= 2 ? 2 : n <= 3 ? 3 : n <= 4 ? 4 : n <= 5 ? 5 : n <= 8 ? 8 : 10;
  return step * exp;
}

/** Solid greys per series; the third is hatched so it reads without colour. */
function fillFor(index: number, patternId: string) {
  return index === 2 ? `url(#${patternId})` : (GREYS[index] ?? GREYS[4] ?? "");
}

function Defs({ patternId }: { patternId: string }) {
  return (
    <defs>
      <pattern id={patternId} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="6" height="6" fill="var(--color-chart-5)" />
        <line x1="0" y1="0" x2="0" y2="6" stroke="var(--color-chart-1)" strokeWidth="2.5" />
      </pattern>
    </defs>
  );
}

export function Legend({ items, patternId }: { items: { label: string; index: number }[]; patternId: string }) {
  if (items.length < 2) return null;
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-secondary" aria-hidden>
      {items.map((s) => (
        <li key={s.label} className="inline-flex items-center gap-1.5">
          <svg className="size-3" viewBox="0 0 12 12">
            <Defs patternId={`${patternId}-l`} />
            <rect width="12" height="12" rx="2" fill={fillFor(s.index, `${patternId}-l`)} />
          </svg>
          {s.label}
        </li>
      ))}
    </ul>
  );
}

function DataTable({ caption, head, rows }: { caption: string; head: string[]; rows: (string | number)[][] }) {
  return (
    <table className="sr-only">
      <caption>{caption}</caption>
      <thead>
        <tr>{head.map((h) => <th key={h} scope="col">{h}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>{r.map((c, j) => (j === 0 ? <th key={j} scope="row">{c}</th> : <td key={j}>{c}</td>))}</tr>
        ))}
      </tbody>
    </table>
  );
}

const HEIGHT = 180;
const PAD = { top: 12, right: 8, bottom: 22, left: 48 };

export interface BarChartProps {
  /** Accessible summary, e.g. "Spend per day, last 30 days, highest 4.10 dollars on 2 Nov". */
  summary: string;
  dates: string[];
  series: Series[];
  stacked?: boolean;
  format: (n: number) => string;
  /** A reference line (the daily cap). */
  line?: { value: number; label: string };
  /** Days to mark (at or over 80% of the cap): darkest grey and a note in the tooltip. */
  flagged?: (index: number) => string | null;
}

/** Bars per day. Hover or arrow keys pick a day; the tooltip reads it out politely. */
export function BarChart({ summary, dates, series, stacked = false, format, line, flagged }: BarChartProps) {
  const { ref, width } = useWidth(640);
  const patternId = `bars-${useId().replace(/:/g, "")}`;
  const [active, setActive] = useState<number | null>(null);
  const n = dates.length;
  const plotW = Math.max(10, width - PAD.left - PAD.right);
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const totals = dates.map((_, i) => series.reduce((sum, s) => sum + (s.values[i] ?? 0), 0));
  const peak = stacked ? Math.max(0, ...totals) : Math.max(0, ...series.flatMap((s) => s.values));
  // The cap joins the scale only when spend comes near it; otherwise it would flatten the bars,
  // so it is named under the chart instead.
  const lineOnScale = line !== undefined && line.value > 0 && line.value <= peak * 2;
  // Counts get whole-number ticks: no "0.5 users".
  const whole = series.every((x) => x.values.every((v) => Number.isInteger(v)));
  const raw = niceMax(Math.max(peak, lineOnScale ? line.value : 0));
  const top = whole ? Math.max(2, Math.ceil(raw / 2) * 2) : raw;
  const y = (v: number) => PAD.top + plotH - (v / top) * plotH;
  const band = plotW / Math.max(1, n);
  const groupW = Math.max(1, band * (n > 45 ? 0.8 : 0.66));
  const barW = stacked ? groupW : groupW / Math.max(1, series.length);
  const empty = peak === 0;
  // A single series uses a mid grey, so marked days (darkest) stand out.
  const slot = (si: number) => (series.length === 1 ? 1 : si);

  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    const last = n - 1;
    const next =
      e.key === "ArrowRight" ? Math.min(last, (active ?? -1) + 1)
      : e.key === "ArrowLeft" ? Math.max(0, (active ?? n) - 1)
      : e.key === "Home" ? 0
      : e.key === "End" ? last
      : e.key === "Escape" ? null
      : undefined;
    if (next === undefined) return;
    e.preventDefault();
    setActive(next);
  };

  const ticks = [0, top / 2, top];
  const labelDays = n <= 7 ? dates.map((_, i) => i) : [0, Math.floor((n - 1) / 2), n - 1];
  const tipLeft = active === null ? 0 : Math.min(Math.max(PAD.left + band * active + band / 2, 70), width - 70);
  const note = active !== null && flagged ? flagged(active) : null;

  return (
    <div ref={ref} className="relative flex flex-col gap-2">
      <svg
        width={width}
        height={HEIGHT}
        role="group"
        aria-label={summary}
        tabIndex={0}
        onKeyDown={onKey}
        onMouseLeave={() => { setActive(null); }}
        onBlur={() => { setActive(null); }}
        className="block max-w-full touch-pan-y rounded-md outline-none focus-visible:ring-2 focus-visible:ring-focus"
      >
        <Defs patternId={patternId} />
        {ticks.map((t) => (
          <g key={t} aria-hidden>
            <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--color-border)" />
            <text x={PAD.left - 6} y={y(t) + 4} textAnchor="end" className="fill-text-secondary text-[11px] tabular-nums">
              {format(t)}
            </text>
          </g>
        ))}
        {dates.map((date, i) => {
          const x0 = PAD.left + band * i + (band - groupW) / 2;
          let base = 0;
          return (
            <g key={date} aria-hidden opacity={active === null || active === i ? 1 : 0.55}>
              {series.map((s, si) => {
                const v = s.values[i] ?? 0;
                if (v <= 0) return null;
                const yTop = stacked ? y(base + v) : y(v);
                const h = stacked ? y(base) - y(base + v) : y(0) - y(v);
                const x = stacked ? x0 : x0 + si * barW;
                base += v;
                const mark = flagged?.(i) && si === 0;
                return <rect key={s.key} x={x} y={yTop} width={Math.max(1, barW - (stacked ? 0 : 1))} height={Math.max(1, h)} rx={Math.min(2, barW / 4)} fill={mark ? "var(--color-text)" : fillFor(slot(si), patternId)} />;
              })}
              {/* The whole band picks the day, so thin bars are easy to hover. */}
              <rect x={PAD.left + band * i} y={PAD.top} width={band} height={plotH} fill="transparent" onMouseEnter={() => { setActive(i); }} />
            </g>
          );
        })}
        {line && lineOnScale && (
          <g aria-hidden>
            <line x1={PAD.left} x2={width - PAD.right} y1={y(line.value)} y2={y(line.value)} stroke="var(--color-text)" strokeDasharray="4 4" />
            <text x={width - PAD.right} y={y(line.value) - 4} textAnchor="end" className="fill-text text-[11px]">{line.label}</text>
          </g>
        )}
        {labelDays.map((i) => (
          <text key={i} aria-hidden x={PAD.left + band * i + band / 2} y={HEIGHT - 6} textAnchor={i === 0 && n > 7 ? "start" : i === n - 1 && n > 7 ? "end" : "middle"} className="fill-text-secondary text-[11px]">
            {shortDate(dates[i] ?? "")}
          </text>
        ))}
        {empty && (
          <text x={PAD.left + plotW / 2} y={PAD.top + plotH / 2} textAnchor="middle" className="fill-text-secondary text-sm">No usage yet</text>
        )}
      </svg>
      <div aria-live="polite" className="sr-only">
        {active !== null && `${shortDate(dates[active] ?? "")}: ${series.map((s) => `${s.label} ${format(s.values[active] ?? 0)}`).join(", ")}${note ? `. ${note}` : ""}`}
      </div>
      {active !== null && (
        <div aria-hidden className="pointer-events-none absolute top-0 z-10 -translate-x-1/2 rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs shadow-card" style={{ left: tipLeft }}>
          <p className="font-medium">{shortDate(dates[active] ?? "")}</p>
          {series.map((s) => (
            <p key={s.key} className="whitespace-nowrap tabular-nums text-text-secondary">
              {series.length > 1 ? `${s.label}: ` : ""}<span className="text-text">{format(s.values[active] ?? 0)}</span>
            </p>
          ))}
          {note && (
            <p className="mt-0.5 inline-flex items-center gap-1 whitespace-nowrap">
              <TriangleAlert aria-hidden className="size-3" /> {note}
            </p>
          )}
        </div>
      )}
      <Legend patternId={patternId} items={series.map((s, i) => ({ label: s.label, index: slot(i) }))} />
      {line && line.value > 0 && !lineOnScale && !empty && (
        <p className="text-xs text-text-secondary">{`${line.label}, well above this range`}</p>
      )}
      <DataTable
        caption={summary}
        head={["Day", ...series.map((s) => s.label)]}
        rows={dates.map((d, i) => [shortDate(d), ...series.map((s) => format(s.values[i] ?? 0))])}
      />
    </div>
  );
}

export interface Slice {
  name: string;
  value: number;
  /** Opens the matching admin page (jobs or plans). */
  to?: "/app/admin/jobs" | "/app/admin/plans";
}

/** A ring with the total in the middle and a legend with values; at most five slices plus Other. */
export function Donut({ summary, slices, format, total: totalLabel }: { summary: string; slices: Slice[]; format: (n: number) => string; total: string }) {
  const [hover, setHover] = useState<string | null>(null);
  const total = slices.reduce((s, x) => s + x.value, 0);
  const R = 52;
  const C = 2 * Math.PI * R;
  let offset = 0;
  return (
    <figure aria-label={summary} className="flex flex-col items-center gap-4">
      <div className="relative size-36 shrink-0">
        <svg viewBox="0 0 140 140" className="size-36 -rotate-90" aria-hidden>
          <circle cx="70" cy="70" r={R} fill="none" stroke="var(--color-muted)" strokeWidth="20" />
          {total > 0 &&
            slices.map((s, i) => {
              const len = (s.value / total) * C;
              const el = (
                <circle
                  key={s.name}
                  cx="70"
                  cy="70"
                  r={R}
                  fill="none"
                  stroke={s.name === "Other" ? "var(--color-chart-5)" : (GREYS[i] ?? "")}
                  strokeWidth={hover === s.name ? 24 : 20}
                  strokeDasharray={`${String(Math.max(0, len - (slices.length > 1 ? 1.5 : 0)))} ${String(C)}`}
                  strokeDashoffset={-offset}
                  onMouseEnter={() => { setHover(s.name); }}
                  onMouseLeave={() => { setHover(null); }}
                  className="transition-[stroke-width] duration-150 motion-reduce:transition-none"
                />
              );
              offset += len;
              return el;
            })}
        </svg>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="font-display text-lg font-bold tabular-nums">{total > 0 ? format(total) : "0"}</span>
          <span className="text-xs text-text-secondary">{totalLabel}</span>
        </div>
      </div>
      {total === 0 ? (
        <p className="text-sm text-text-secondary">No usage yet</p>
      ) : (
        <ul className="flex w-full min-w-0 flex-col gap-1 text-sm">
          {slices.map((s, i) => {
            const pct = `${String(Math.round((s.value / total) * 100))}%`;
            const body: ReactNode = (
              <>
                <span aria-hidden className="size-2.5 shrink-0 rounded-sm" style={{ background: s.name === "Other" ? "var(--color-chart-5)" : GREYS[i] }} />
                <span className="min-w-0 flex-1 truncate" title={s.name}>{s.name}</span>
                <span className="shrink-0 tabular-nums text-text-secondary">{pct}</span>
                <span className="w-16 shrink-0 text-right tabular-nums">{format(s.value)}</span>
              </>
            );
            const cls = `flex min-h-9 min-w-0 items-center gap-2 rounded-md px-1.5 ${hover === s.name ? "bg-muted" : ""}`;
            return (
              <li key={s.name} onMouseEnter={() => { setHover(s.name); }} onMouseLeave={() => { setHover(null); }}>
                {s.to ? (
                  <Link to={s.to} className={`${cls} hover:bg-muted focus-visible:bg-muted`} onFocus={() => { setHover(s.name); }} onBlur={() => { setHover(null); }}>
                    {body}
                  </Link>
                ) : (
                  <div className={cls}>{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </figure>
  );
}

export type RangeKey = "7d" | "30d" | "90d";
const RANGE_LABELS: Record<RangeKey, string> = { "7d": "7 days", "30d": "30 days", "90d": "90 days" };

/** 7, 30 or 90 days as a segmented control (radio group, arrow keys move). */
export function RangeSwitch({ value, onChange }: { value: RangeKey; onChange: (next: RangeKey) => void }) {
  const keys = Object.keys(RANGE_LABELS) as RangeKey[];
  return (
    <div role="radiogroup" aria-label="Range" className="inline-flex rounded-pill border border-border p-1">
      {keys.map((k, i) => (
        <button
          key={k}
          type="button"
          role="radio"
          aria-checked={value === k}
          tabIndex={value === k ? 0 : -1}
          onClick={() => { onChange(k); }}
          onKeyDown={(e) => {
            const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
            if (!step) return;
            e.preventDefault();
            const next = keys[(i + step + keys.length) % keys.length];
            if (next) onChange(next);
          }}
          className={`inline-flex min-h-9 items-center rounded-pill px-3 text-sm ${value === k ? "bg-primary text-primary-text" : "text-text-secondary hover:text-text"}`}
        >
          {RANGE_LABELS[k]}
        </button>
      ))}
    </div>
  );
}
