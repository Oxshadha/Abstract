import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { timeLeft } from "./time-left";

/** Counts down between polls so the estimate moves every second, never below one second. */
function useCountdown(seconds: number | null | undefined): number | null {
  const [left, setLeft] = useState<number | null>(seconds ?? null);
  const [from, setFrom] = useState(seconds);
  if (from !== seconds) {
    setFrom(seconds);
    setLeft(seconds ?? null);
  }
  useEffect(() => {
    if (seconds == null) return;
    const id = setInterval(() => { setLeft((s) => (s == null ? s : Math.max(1, s - 1))); }, 1000);
    return () => { clearInterval(id); };
  }, [seconds]);
  return left;
}

/**
 * Progress of the background search for tables and figures (spec 009 AC2): a bar with the page
 * being read and an estimate of the time left, the same on phones and desktop.
 */
export function EnrichProgress({ done, total, secondsLeft }: { done: number; total: number | null; secondsLeft?: number | null }) {
  const left = useCountdown(secondsLeft);
  if (!total) {
    return (
      <p role="status" className="flex items-center gap-2">
        <Loader2 aria-hidden className="size-4 shrink-0 animate-spin motion-reduce:animate-none" />
        Getting ready to find tables and figures
      </p>
    );
  }
  const page = Math.min(done + 1, total);
  const percent = Math.round((Math.min(done, total) / total) * 100);
  const eta = left == null ? "" : timeLeft(left);
  return (
    <div role="status" className="flex flex-col gap-2">
      <p className="flex min-w-0 items-center gap-2">
        <Loader2 aria-hidden className="size-4 shrink-0 animate-spin motion-reduce:animate-none" />
        <span className="min-w-0 flex-1 truncate text-text">Finding tables and figures</span>
        {eta && <span className="shrink-0 tabular-nums">{eta}</span>}
      </p>
      <div
        role="progressbar"
        aria-label="Finding tables and figures"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={Math.min(done, total)}
        aria-valuetext={`Page ${String(page)} of ${String(total)}${eta ? `, ${eta}` : ""}`}
        className="h-1.5 w-full overflow-hidden rounded-pill bg-muted"
      >
        <div className="h-full rounded-pill bg-primary transition-[width] duration-500 motion-reduce:transition-none" style={{ width: `${String(Math.max(4, percent))}%` }} />
      </div>
      <p className="text-xs">{`Page ${String(page)} of ${String(total)}. You can keep reading; they appear here when ready.`}</p>
    </div>
  );
}
