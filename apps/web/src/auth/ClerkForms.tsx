import { SignIn, SignUp } from "@clerk/react";

import { clerkAppearance, useCurrentTheme } from "./clerkAppearance";

/** Lazily loaded Clerk forms (separate chunk, only when Clerk is configured). */
export default function ClerkForms({ mode, routing }: { mode: "sign-in" | "sign-up"; routing: "hash" | "path" }) {
  const appearance = clerkAppearance(useCurrentTheme());
  if (mode === "sign-in") {
    return routing === "path" ? (
      <SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" appearance={appearance} />
    ) : (
      <SignIn routing="hash" signUpUrl="/sign-up" appearance={appearance} />
    );
  }
  return routing === "path" ? (
    <SignUp routing="path" path="/sign-up" signInUrl="/sign-in" appearance={appearance} />
  ) : (
    <SignUp routing="hash" signInUrl="/sign-in" appearance={appearance} />
  );
}
