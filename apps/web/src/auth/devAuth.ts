import { apiBaseUrl } from "@/api/client";

import { configureAuth, devTokenSource } from "./session";
import { setAuthState } from "./state";

const DEV_FLAG = "abstract.dev-signed-in"; // a flag only; the token itself stays in memory

function readDevFlag(): boolean {
  try {
    return window.sessionStorage.getItem(DEV_FLAG) === "1";
  } catch {
    return false;
  }
}

function writeDevFlag(signedIn: boolean): void {
  try {
    if (signedIn) window.sessionStorage.setItem(DEV_FLAG, "1");
    else window.sessionStorage.removeItem(DEV_FLAG);
  } catch {
    // storage blocked: the choice lasts for this page only
  }
}

let devConfigured = false;

/** Development login (D70): explicit "Continue as demo user", explicit sign out. */
export function configureDevAuth(): void {
  if (devConfigured) return;
  devConfigured = true;
  const dev = devTokenSource(apiBaseUrl);
  // A 401 in dev means the API restarted with a new secret: refetch the token silently.
  configureAuth(dev.source, dev.reset);
  setAuthState({
    provider: "dev",
    status: readDevFlag() ? "signed-in" : "signed-out",
    signIn: () => {
      writeDevFlag(true);
      setAuthState({ status: "signed-in" });
    },
    signOut: () => {
      writeDevFlag(false);
      dev.reset();
      setAuthState({ status: "signed-out" });
    },
  });
}

/** For tests: start the dev login from a clean state. */
export function resetDevAuthForTests(): void {
  devConfigured = false;
  writeDevFlag(false);
}
