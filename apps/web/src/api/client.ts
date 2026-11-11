import createClient, { type Middleware } from "openapi-fetch";

import { currentToken, notifyUnauthorized } from "@/auth/session";

import type { paths } from "./schema";

export const apiBaseUrl: string = import.meta.env.VITE_API_BASE_URL ?? window.location.origin;

/** Attaches the session token to every request; a 401 ends the local session (AC14). */
export const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const token = await currentToken();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401) notifyUnauthorized();
    return response;
  },
};

/**
 * Typed API client generated from the FastAPI OpenAPI schema (spec 001 AC9).
 * Base URL is explicit: same origin by default (Vite proxies /api in dev), or VITE_API_BASE_URL.
 */
export const api = createClient<paths>({
  baseUrl: apiBaseUrl,
  // Resolve fetch at call time (not import time) so polyfills and test stubs are honoured.
  fetch: (request) => globalThis.fetch(request),
});
api.use(authMiddleware);
