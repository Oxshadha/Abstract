import { useAuth } from "@clerk/react";
import { useEffect } from "react";

import { configureAuth } from "./session";

/** Connects Clerk's session to the API client: getToken() per request, sign out on 401. */
export function ClerkBridge() {
  const { getToken, signOut } = useAuth();
  useEffect(() => {
    configureAuth(
      () => getToken(),
      () => {
        void signOut();
      },
    );
  }, [getToken, signOut]);
  return null;
}
