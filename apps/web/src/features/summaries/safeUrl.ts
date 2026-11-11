const SAFE_PROTOCOL = /^(https?:|mailto:)/i;

/** Only http(s) and mailto links survive (spec 006 AC14); anything else becomes inert. */
export function safeUrl(url: string): string {
  return SAFE_PROTOCOL.test(url.trim()) ? url : "";
}
