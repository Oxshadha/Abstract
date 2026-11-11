/**
 * Auth session for API calls (spec 002 AC14).
 * One token source is active: Clerk (when VITE_CLERK_PUBLISHABLE_KEY is set) or the
 * development login (D70). Tokens live in memory only, never in localStorage.
 */
export type TokenSource = () => Promise<string | null>;

let tokenSource: TokenSource = () => Promise.resolve(null);
let unauthorizedHandler: () => void = () => undefined;

export function configureAuth(source: TokenSource, onUnauthorized: () => void): void {
  tokenSource = source;
  unauthorizedHandler = onUnauthorized;
}

export function currentToken(): Promise<string | null> {
  return tokenSource();
}

export function notifyUnauthorized(): void {
  unauthorizedHandler();
}

/** Development login: fetches a demo-user token and caches it in memory until a 401. */
export function devTokenSource(baseUrl: string): { source: TokenSource; reset: () => void } {
  let cached: Promise<string | null> | null = null;
  const fetchToken = async (): Promise<string | null> => {
    const response = await globalThis.fetch(`${baseUrl}/api/v1/dev/token`, { method: "POST" });
    if (!response.ok) return null;
    const body = (await response.json()) as { token?: string };
    return body.token ?? null;
  };
  return {
    source: () => (cached ??= fetchToken()),
    reset: () => {
      cached = null;
    },
  };
}
