import { lazy, Suspense, type ReactNode } from "react";

import { apiBaseUrl } from "@/api/client";

import { configureAuth, devTokenSource } from "./session";

const clerkKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
// Clerk is only downloaded when it is configured (AC10); the dev login needs none of it.
const ClerkAuth = lazy(() => import("./ClerkAuth"));

/** Clerk when a publishable key is configured, otherwise the development login (D70). */
export function AuthBoundary({ children }: { children: ReactNode }) {
  if (clerkKey) {
    return (
      <Suspense fallback={null}>
        <ClerkAuth publishableKey={clerkKey}>{children}</ClerkAuth>
      </Suspense>
    );
  }
  // No Clerk key: development login with a seeded demo user (D70). The API refuses this mode
  // in production, so it cannot be enabled there by mistake.
  const dev = devTokenSource(apiBaseUrl);
  configureAuth(dev.source, dev.reset);
  return <>{children}</>;
}
