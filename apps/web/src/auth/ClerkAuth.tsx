import { ClerkProvider } from "@clerk/react";
import type { ReactNode } from "react";

import { ClerkBridge } from "./ClerkBridge";

/** Our product name and wording on Clerk's forms, whatever the Clerk application is called. */
const localization = {
  signIn: { start: { title: "Sign in to abstract.", subtitle: "Welcome back. Sign in to continue." } },
  signUp: { start: { title: "Create your account", subtitle: "Start reading papers with abstract." } },
};

/** Lazily loaded Clerk wrapper (separate chunk). */
export default function ClerkAuth({ publishableKey, children }: { publishableKey: string; children: ReactNode }) {
  return (
    <ClerkProvider
      publishableKey={publishableKey}
      localization={localization}
      // After signing in or up, straight into the app (not back to the landing page).
      signInFallbackRedirectUrl="/app/home"
      signUpFallbackRedirectUrl="/app/home"
    >
      <ClerkBridge />
      {children}
    </ClerkProvider>
  );
}
