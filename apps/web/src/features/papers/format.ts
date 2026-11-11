export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${String(bytes)} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];

/** "2h ago" style, as in the Library mockup. */
export function timeAgo(iso: string, now: number = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const short: Partial<Record<Intl.RelativeTimeFormatUnit, string>> = { day: "d", hour: "h", minute: "m" };
  for (const [unit, size] of UNITS) {
    if (seconds >= size) return `${String(Math.floor(seconds / size))}${short[unit] ?? ""} ago`;
  }
  return "just now";
}
