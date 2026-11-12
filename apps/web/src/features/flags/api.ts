import { useQuery } from "@tanstack/react-query";

import { fetchMe } from "@/api/me";
import { useAuthState } from "@/auth/state";

import { getFlags } from "./client";

export type FlagKey = "figures" | "search" | "reading_aids";


/**
 * Spec 011 AC6: whether a feature is on for the caller. On while loading or if the flags cannot be
 * read (the API still refuses a feature that is off), so nothing flickers away on a slow network.
 */
export function useFlag(key: FlagKey): boolean {
  const auth = useAuthState();
  const flags = useQuery({ queryKey: ["me", "flags"], queryFn: getFlags, enabled: auth.status === "signed-in", staleTime: 60_000 });
  return flags.data?.[key] ?? true;
}

/** Platform admins see the Admin area (spec 011 AC1). */
export function useIsAdmin(): boolean {
  const auth = useAuthState();
  const me = useQuery({ queryKey: ["me"], queryFn: fetchMe, enabled: auth.status === "signed-in" });
  return me.data?.user.platform_role === "admin";
}
