import { useSyncExternalStore } from "react";

/**
 * Provider-neutral sign-in state (spec 003 AC8): Clerk or the development login (D70) publish
 * their status and actions here; UI reads it through useAuthState().
 */
export type AuthStatus = "loading" | "signed-in" | "signed-out";

interface AuthState {
  status: AuthStatus;
  provider: "dev" | "clerk";
  signIn: () => void;
  signOut: () => void;
}

let state: AuthState = {
  status: "loading",
  provider: "dev",
  signIn: () => undefined,
  signOut: () => undefined,
};
const listeners = new Set<() => void>();

export function setAuthState(patch: Partial<AuthState>): void {
  state = { ...state, ...patch };
  listeners.forEach((listener) => {
    listener();
  });
}

export function useAuthState(): AuthState {
  return useSyncExternalStore(
    (onChange) => {
      listeners.add(onChange);
      return () => listeners.delete(onChange);
    },
    () => state,
  );
}
