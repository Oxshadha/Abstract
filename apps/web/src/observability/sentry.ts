/**
 * Error monitoring + Core Web Vitals (spec 003 AC12, AC13; D37, D76).
 * Disabled when VITE_SENTRY_DSN is absent. Loaded lazily so the SDK never weighs on the first
 * page load (AC10). Privacy (D76): errors and metadata only.
 */
type SentryModule = typeof import("@sentry/react");
let sentry: Promise<SentryModule> | null = null;

export function initSentry(): boolean {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) return false;
  sentry = import("@sentry/react").then((Sentry) => {
    Sentry.init({
      dsn,
      environment: import.meta.env.MODE,
      release: import.meta.env.VITE_RELEASE,
      // Sentry 11 dataCollection: no user info, cookies, headers, bodies or query strings.
      dataCollection: {
        userInfo: false,
        cookies: false,
        httpHeaders: false,
        httpBodies: [],
        urlQueryParams: false,
      },
      // Browser tracing records LCP, INP and CLS (AC13); sampled to stay within the free tier.
      integrations: [Sentry.browserTracingIntegration()],
      tracesSampleRate: import.meta.env.PROD ? 0.1 : 1.0,
      beforeSend(event) {
        if (event.request) {
          delete event.request.data;
          delete event.request.cookies;
        }
        return event;
      },
    });
    return Sentry;
  });
  return true;
}

/** Report an error caught by an error boundary (no-op when Sentry is off). */
export function reportError(error: unknown, boundary: string): void {
  void sentry?.then((Sentry) => {
    Sentry.withScope((scope) => {
      scope.setTag("boundary", boundary);
      Sentry.captureException(error);
    });
  });
}
