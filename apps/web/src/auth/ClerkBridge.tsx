import { useAuth } from "@clerk/react";
import { useEffect } from "react";

import { configureAuth } from "./session";
import { setAuthState } from "./state";

/** Connects Clerk to the API client and the shared auth state (AC8, AC14 of spec 002). */
export function ClerkBridge() {
  const { isLoaded, isSignedIn, getToken, signOut } = useAuth();
  useEffect(() => {
    configureAuth(
      () => getToken(),
      () => {
        void signOut();
      },
      () => getToken({ skipCache: true }),
    );
    setAuthState({
      provider: "clerk",
      status: !isLoaded ? "loading" : isSignedIn ? "signed-in" : "signed-out",
      signIn: () => undefined, // the gate shows Clerk's sign-in form when signed out
      signOut: () => {
        void signOut();
      },
    });
  }, [isLoaded, isSignedIn, getToken, signOut]);
  return null;
}
