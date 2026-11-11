import { AlertTriangle, CheckCircle2, Info, Loader2, XCircle } from "lucide-react";
import type { ReactNode } from "react";

/**
 * The only place status colours appear in pills (D44, spec 003 AC5).
 * "processing" is deliberately neutral grey: ordinary activity is not a colour event.
 */
export type Status = "success" | "warning" | "error" | "info" | "processing" | "neutral";

const STYLES: Record<Status, string> = {
  success: "bg-success-bg text-success",
  warning: "bg-warning-bg text-warning",
  error: "bg-error-bg text-error",
  info: "bg-info-bg text-info",
  processing: "bg-muted text-text-secondary",
  neutral: "bg-muted text-text-secondary",
};

const ICONS: Record<Status, typeof Info | null> = {
  success: CheckCircle2,
  warning: AlertTriangle,
  error: XCircle,
  info: Info,
  processing: Loader2,
  neutral: null,
};

export function StatusPill({ status, children }: { status: Status; children: ReactNode }) {
  const Icon = ICONS[status];
  return (
    <span
      role={status === "processing" ? "status" : undefined}
      className={`inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 text-sm font-medium ${STYLES[status]}`}
    >
      {Icon && (
        <Icon
          aria-hidden
          className={`size-4 ${status === "processing" ? "animate-spin motion-reduce:animate-none" : ""}`}
        />
      )}
      {children}
    </span>
  );
}
