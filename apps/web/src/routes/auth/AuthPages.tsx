import { Navigate } from "@tanstack/react-router";

import { AuthCard, AuthClose } from "@/auth/AuthCard";
import { useAuthState } from "@/auth/state";

/** The Workspace, blurred behind the sign-in card on desktop, like the dialog over the app (D96). */
function Backdrop() {
  return (
    <picture aria-hidden className="pointer-events-none absolute inset-0 hidden lg:block">
      <source media="(prefers-color-scheme: dark)" type="image/webp" srcSet="/landing/workspace-dark-1600.webp" />
      <img src="/landing/workspace-light-1600.webp" alt="" className="size-full scale-105 object-cover blur-md" />
    </picture>
  );
}

/**
 * Sign in and sign up as their own pages. Desktop: the two-column card (liquid wordmark and form)
 * floats over the blurred Workspace. Phones: the form card on its own, as before.
 */
function AuthPage({ mode }: { mode: "sign-in" | "sign-up" }) {
  const { status } = useAuthState();
  if (status === "signed-in") return <Navigate to="/app/home" />;
  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden bg-bg p-4 text-text sm:p-6">
      <Backdrop />
      <div aria-hidden className="absolute inset-0 hidden bg-text/30 lg:block" />
      <main className="relative w-full max-w-md overflow-hidden rounded-xl bg-surface p-8 shadow-card lg:max-w-5xl lg:p-0 lg:shadow-overlay">
        <AuthClose />
        <AuthCard mode={mode} routing="path" />
      </main>
    </div>
  );
}

export function SignInPage() {
  return <AuthPage mode="sign-in" />;
}

export function SignUpPage() {
  return <AuthPage mode="sign-up" />;
}
