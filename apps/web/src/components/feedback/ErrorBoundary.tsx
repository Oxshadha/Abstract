import { RotateCcw } from "lucide-react";
import { Component, type ReactNode } from "react";

import { reportError } from "@/observability/sentry";

interface Props {
  name: string;
  children: ReactNode;
}

/**
 * Error boundary for a route or panel (spec 003 AC11): reports to Sentry when configured and
 * offers "Try again" without reloading the app. Our own class (not Sentry's component) so the
 * Sentry SDK stays out of the entry bundle (AC10).
 */
export class ErrorBoundary extends Component<Props, { failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  override componentDidCatch(error: Error): void {
    reportError(error, this.props.name);
  }

  override render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" className="flex flex-col items-start gap-3 rounded-lg border border-border bg-surface p-4">
        <p className="font-medium">Something went wrong in {this.props.name}.</p>
        <p className="text-sm text-text-secondary">The rest of the page still works. You can try this part again.</p>
        <button
          type="button"
          onClick={() => {
            this.setState({ failed: false });
          }}
          className="inline-flex min-h-11 items-center gap-2 rounded-pill border border-border-strong px-4"
        >
          <RotateCcw aria-hidden className="size-4" />
          Try again
        </button>
      </div>
    );
  }
}
