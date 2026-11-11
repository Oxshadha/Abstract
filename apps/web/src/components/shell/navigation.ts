import { Home, Layers, LayoutGrid, Settings } from "lucide-react";

export const NAV_ITEMS = [
  { to: "/app/library", label: "Library", Icon: Home },
  { to: "/app/collections", label: "Collections", Icon: Layers },
  { to: "/app/templates", label: "Templates", Icon: LayoutGrid },
  { to: "/app/settings", label: "Settings", Icon: Settings },
] as const;
