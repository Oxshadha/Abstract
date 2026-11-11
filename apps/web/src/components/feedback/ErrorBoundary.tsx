import * as Sentry from "@sentry/react";
import { RotateCcw } from "lucide-react";
import type { ReactNode } from "react";

/**
 * Error boundary for a route or panel (spec 003 AC11): reports to Sentry (when configured)
 * and offers "Try again" without reloading the whole app.
 */
export function ErrorBoundary({ name, children }: { name: string; children: ReactNode }) {
  return (
    <Sentry.ErrorBoundary
      beforeCapture={(scope) => {
        scope.setTag("boundary", name);
      }}
      fallback={(fallback) => (
        <div role="alert" className="flex flex-col items-start gap-3 rounded-lg border border-border bg-surface p-4">
          <p className="font-medium">Something went wrong in {name}.</p>
          <p className="text-sm text-text-secondary">The rest of the page still works. You can try this part again.</p>
          <button
            type="button"
            onClick={() => {
              fallback.resetError();
            }}
            className="inline-flex min-h-11 items-center gap-2 rounded-pill border border-border-strong px-4"
          >
            <RotateCcw aria-hidden className="size-4" />
            Try again
          </button>
        </div>
      )}
    >
      {children}
    </Sentry.ErrorBoundary>
  );
}
