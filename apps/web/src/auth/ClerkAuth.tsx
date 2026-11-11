import { ClerkProvider } from "@clerk/react";
import type { ReactNode } from "react";

import { ClerkBridge } from "./ClerkBridge";

/** Lazily loaded Clerk wrapper (separate chunk). */
export default function ClerkAuth({ publishableKey, children }: { publishableKey: string; children: ReactNode }) {
  return (
    <ClerkProvider publishableKey={publishableKey}>
      <ClerkBridge />
      {children}
    </ClerkProvider>
  );
}
