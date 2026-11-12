import { HttpError } from "./queryClient";

interface ProblemBody {
  detail?: unknown;
  resets_at?: unknown;
}

/**
 * A usage limit (spec 012 AC3) says when it resets in UTC; readers see their own time:
 * "It resets at midnight UTC." becomes "It resets at 5:30 AM.", a monthly one "It resets on 1 Dec.".
 */
export function localReset(detail: string, resetsAt: string, locale?: string): string {
  const at = new Date(resetsAt);
  if (Number.isNaN(at.getTime()) || !/ It resets .*$/.test(detail)) return detail;
  const monthly = at.getUTCDate() === 1 && /1st/.test(detail);
  const when = monthly
    ? `on ${new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).format(at)}`
    : `at ${new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit" }).format(at)}`;
  return detail.replace(/ It resets .*$/, ` It resets ${when}.`);
}

/** The error to show for a failed API response: its problem detail, or the fallback. */
export async function problem(response: Response, fallback: string): Promise<HttpError> {
  try {
    const body = (await response.clone().json()) as ProblemBody;
    if (typeof body.detail === "string" && body.detail) {
      const detail = typeof body.resets_at === "string" ? localReset(body.detail, body.resets_at) : body.detail;
      return new HttpError(response.status, detail);
    }
  } catch {
    // not JSON
  }
  return new HttpError(response.status, fallback);
}
