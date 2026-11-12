import { Home, Layers, LayoutGrid, Settings, ShieldCheck } from "lucide-react";

import { useIsAdmin } from "@/features/flags/api";

export const NAV_ITEMS = [
  { to: "/app/home", label: "Home", Icon: Home },
  { to: "/app/library", label: "Library", Icon: Layers },
  { to: "/app/templates", label: "Templates", Icon: LayoutGrid },
  { to: "/app/settings", label: "Settings", Icon: Settings },
] as const;

const ADMIN_ITEM = { to: "/app/admin", label: "Admin", Icon: ShieldCheck } as const;

/** The main navigation; platform admins also see Admin (spec 011 AC1). */
export function useNavItems(): readonly (typeof NAV_ITEMS[number] | typeof ADMIN_ITEM)[] {
  return useIsAdmin() ? [...NAV_ITEMS, ADMIN_ITEM] : NAV_ITEMS;
}
