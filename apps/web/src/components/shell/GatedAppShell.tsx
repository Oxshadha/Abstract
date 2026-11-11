import { AuthGate } from "@/auth/AuthGate";

import { AppShell } from "./AppShell";

/** The app shell behind the sign-in gate (spec 003 AC8). */
export function GatedAppShell() {
  return (
    <AuthGate>
      <AppShell />
    </AuthGate>
  );
}
