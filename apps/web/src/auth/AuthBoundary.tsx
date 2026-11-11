import { ClerkProvider } from "@clerk/react";
import type { ReactNode } from "react";

import { apiBaseUrl } from "@/api/client";

import { ClerkBridge } from "./ClerkBridge";
import { configureAuth, devTokenSource } from "./session";

const clerkKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

/** Clerk when a publishable key is configured, otherwise the development login (D70). */
export function AuthBoundary({ children }: { children: ReactNode }) {
  if (clerkKey) {
    return (
      <ClerkProvider publishableKey={clerkKey}>
        <ClerkBridge />
        {children}
      </ClerkProvider>
    );
  }
  // No Clerk key: development login with a seeded demo user (D70). The API refuses this mode
  // in production, so it cannot be enabled there by mistake.
  const dev = devTokenSource(apiBaseUrl);
  configureAuth(dev.source, dev.reset);
  return <>{children}</>;
}
