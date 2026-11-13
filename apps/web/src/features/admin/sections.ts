import { CreditCard, Cpu, Flag, LayoutDashboard, ListChecks, Users } from "lucide-react";

/** Admin sections (spec 011), grouped for the desktop sidebar (spec 018 AC1). */
export const SECTION_GROUPS = [
  {
    label: "Monitor",
    items: [
      { to: "/app/admin", label: "Overview", Icon: LayoutDashboard },
      { to: "/app/admin/jobs", label: "Jobs", Icon: ListChecks },
    ],
  },
  {
    label: "Manage",
    items: [
      { to: "/app/admin/users", label: "Users", Icon: Users },
      { to: "/app/admin/plans", label: "Plans", Icon: CreditCard },
      { to: "/app/admin/models", label: "Models", Icon: Cpu },
      { to: "/app/admin/flags", label: "Flags", Icon: Flag },
    ],
  },
] as const;

export type Section = (typeof SECTION_GROUPS)[number]["items"][number];
export const SECTIONS: readonly Section[] = SECTION_GROUPS.flatMap((g): readonly Section[] => g.items);

export function isActive(pathname: string, to: string): boolean {
  const path = pathname.replace(/\/$/, "");
  return to === "/app/admin" ? path === to : path.startsWith(to);
}
