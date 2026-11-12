/**
 * Whether this browser looks signed in, from what it already holds and with no API call
 * (spec 016 AC5): the development login's session flag, or Clerk's client cookie. A hint only:
 * the app itself checks the session for real.
 */
export function looksSignedIn(): boolean {
  try {
    if (window.sessionStorage.getItem("abstract.dev-signed-in") === "1") return true;
  } catch {
    // storage blocked
  }
  const uat = /(?:^|;\s*)__client_uat=(\d+)/.exec(document.cookie);
  return Boolean(uat && uat[1] !== "0");
}
