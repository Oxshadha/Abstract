import * as Sentry from "@sentry/react";

/**
 * Error monitoring + Core Web Vitals (spec 003 AC12, AC13; D37, D76).
 * Disabled when VITE_SENTRY_DSN is absent. Privacy (D76): errors and metadata only, no
 * personal data, no request/response bodies, no session replay.
 */
export function initSentry(): boolean {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) return false;
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
  return true;
}
