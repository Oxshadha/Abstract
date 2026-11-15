import createClient, { type Middleware } from "openapi-fetch";

import { currentToken, notifyUnauthorized, refreshToken } from "@/auth/session";

import type { paths } from "./schema";

export const apiBaseUrl: string = import.meta.env.VITE_API_BASE_URL ?? window.location.origin;

/** Attaches the session token to every request (spec 002 AC14). */
export const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const token = await currentToken();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
};

/**
 * openapi-fetch reads an error response's body itself, so it cannot be read again afterwards.
 * Keep an unread copy of every error response for `problem()` to show its detail.
 */
const errorCopies = new WeakMap<Response, Response>();

export const errorBodyMiddleware: Middleware = {
  onResponse({ response }) {
    if (!response.ok) errorCopies.set(response, response.clone());
    return response;
  },
};

/** An unread copy of an error response (or the response itself if none was kept). */
export function readableError(response: Response): Response {
  return (errorCopies.get(response) ?? response).clone();
}

/**
 * On a 401, get a fresh token once and retry; end the session only if the retry is also
 * rejected. A transient 401 (expired cached token, clock skew) never signs the user out.
 */
export async function fetchWithAuthRetry(request: Request): Promise<Response> {
  const retry = request.clone();
  const response = await globalThis.fetch(request);
  if (response.status !== 401) return response;
  const fresh = await refreshToken();
  if (fresh) {
    retry.headers.set("Authorization", `Bearer ${fresh}`);
    const second = await globalThis.fetch(retry);
    if (second.status !== 401) return second;
    notifyUnauthorized();
    return second;
  }
  notifyUnauthorized();
  return response;
}

/**
 * Typed API client generated from the FastAPI OpenAPI schema (spec 001 AC9).
 * Base URL is explicit: same origin by default (Vite proxies /api in dev), or VITE_API_BASE_URL.
 */
export const api = createClient<paths>({
  baseUrl: apiBaseUrl,
  // Resolved at call time (not import time) so polyfills and test stubs are honoured.
  fetch: fetchWithAuthRetry,
});
api.use(authMiddleware, errorBodyMiddleware);
