import { QueryClient } from "@tanstack/react-query";

/** Errors that carry an HTTP status (thrown by API helpers). */
export class HttpError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/**
 * Query defaults (spec 003 AC9): 30 s staleness, never retry 4xx (the request itself is wrong
 * or forbidden), at most 2 retries with backoff for network and 5xx errors, and no refetch on
 * window focus unless a query opts in (job status).
 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof HttpError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 2;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: shouldRetry,
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
        refetchOnWindowFocus: false,
      },
      mutations: { retry: false },
    },
  });
}
