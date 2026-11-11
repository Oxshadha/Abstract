import type { ReactNode } from "react";

import { AuthPanel } from "./AuthPanel";
import { useAuthState } from "./state";

/**
 * Signed-out users see the blurred, inert app with a sign-in dialog on top (D45, AC8).
 * The page underneath cannot be focused or clicked while the dialog is open.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { status } = useAuthState();
  const signedOut = status === "signed-out";
  return (
    <>
      <div inert={signedOut} aria-hidden={signedOut || undefined} className={signedOut ? "pointer-events-none blur-sm select-none" : undefined}>
        {children}
      </div>
      {signedOut && (
        <div className="fixed inset-0 z-40 flex items-end justify-center bg-text/30 sm:items-center">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="auth-title"
            className="w-full max-w-md rounded-t-xl bg-surface p-8 shadow-overlay sm:rounded-xl"
          >
            <AuthPanel mode="sign-in" routing="hash" />
          </div>
        </div>
      )}
    </>
  );
}
