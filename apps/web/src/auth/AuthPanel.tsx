import { lazy, Suspense } from "react";

import { LogoMark } from "@/components/brand/Logo";

import { useAuthState } from "./state";

const ClerkForms = lazy(() => import("./ClerkForms"));

/** Sign-in content shared by the modal and the full-page routes (AC8). */
export function AuthPanel({ mode, routing }: { mode: "sign-in" | "sign-up"; routing: "hash" | "path" }) {
  const auth = useAuthState();
  if (auth.provider === "clerk") {
    return (
      <Suspense fallback={<p className="text-text-secondary">Loading sign-in</p>}>
        <ClerkForms mode={mode} routing={routing} />
      </Suspense>
    );
  }
  return (
    <div className="flex flex-col items-center gap-4 text-center">
      <LogoMark className="size-14" />
      <h2 id="auth-title" className="font-display text-2xl font-bold">
        {mode === "sign-in" ? "Welcome back" : "Create your account"}
      </h2>
      <p className="max-w-sm text-text-secondary">
        This is a development build without sign-in configured. Continue as the demo researcher to explore Abstract.
      </p>
      <button
        type="button"
        onClick={auth.signIn}
        className="inline-flex min-h-11 w-full max-w-xs items-center justify-center rounded-pill bg-primary px-6 font-medium text-primary-text"
      >
        Continue as demo user
      </button>
    </div>
  );
}
