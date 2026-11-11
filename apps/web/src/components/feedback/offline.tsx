import { WifiOff } from "lucide-react";
import { useOnline } from "./useOnline";

/** Calm banner while offline (spec 003 AC14). Neutral colours: being offline is not an error. */
export function OfflineBanner() {
  const online = useOnline();
  if (online) return null;
  return (
    <div role="status" className="flex items-center justify-center gap-2 bg-muted px-4 py-2 text-sm text-text">
      <WifiOff aria-hidden className="size-4" />
      You are offline. Changes are paused until your connection returns.
    </div>
  );
}
