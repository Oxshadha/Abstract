import type { Meter } from "./api";

/** "Resets at 5:30 AM" for a daily meter, "Resets on 1 Dec" for a monthly one, local time. */
export function resetLabel(meter: Pick<Meter, "key" | "resets_at">, locale?: string): string {
  const at = new Date(meter.resets_at);
  if (meter.key === "papers") {
    return `Resets on ${new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).format(at)}`;
  }
  return `Resets at ${new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit" }).format(at)}`;
}

/** The value beside a meter: "3 of 20", "40% of today's allowance" or "No limit". */
export function meterValue(meter: Pick<Meter, "key" | "used" | "limit">): string {
  if (meter.limit == null) return "No limit";
  if (meter.key === "ai") return `${String(meter.used ?? 0)}% of today's allowance`;
  return `${String(meter.used ?? 0)} of ${String(meter.limit)}`;
}

export const METER_LABELS: Record<Meter["key"], string> = {
  papers: "Papers this month",
  messages: "Questions today",
  ai: "AI use today",
};
