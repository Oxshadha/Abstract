import type { Paper } from "@/features/papers/api";

export function paperName(paper: Paper): string {
  return paper.title ?? paper.filename;
}

const DAY = 24 * 60 * 60 * 1000;

/** "Deletes in 3 days" from the server's purge time (spec 019 AC3); the UI never computes it. */
export function deletesIn(purgeAt: string, now = Date.now()): string {
  const days = Math.ceil((new Date(purgeAt).getTime() - now) / DAY);
  if (days <= 0) return "Deletes today";
  return days === 1 ? "Deletes in 1 day" : `Deletes in ${String(days)} days`;
}
