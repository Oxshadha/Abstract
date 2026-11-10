import createClient from "openapi-fetch";

import type { paths } from "./schema";

/**
 * Typed API client generated from the FastAPI OpenAPI schema (spec 001 AC9).
 * Base URL is explicit: same origin by default (Vite proxies /api in dev), or VITE_API_BASE_URL.
 */
export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? window.location.origin,
  // Resolve fetch at call time (not import time) so polyfills and test stubs are honoured.
  fetch: (request) => globalThis.fetch(request),
});
