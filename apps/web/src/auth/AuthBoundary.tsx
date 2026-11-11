import { lazy, Suspense, type ReactNode } from "react";

import { configureDevAuth } from "./devAuth";

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
  configureDevAuth();
  return <>{children}</>;
}
