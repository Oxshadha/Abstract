import { useQuery } from "@tanstack/react-query";
import { Link, Outlet, useRouterState } from "@tanstack/react-router";

import { fetchMe } from "@/api/me";
import { ListRowSkeleton, Loading } from "@/components/feedback/Skeleton";
import { NotFoundPage } from "@/routes/app/pages";

const SECTIONS = [
  { to: "/app/admin", label: "Overview" },
  { to: "/app/admin/users", label: "Users" },
  { to: "/app/admin/plans", label: "Plans" },
  { to: "/app/admin/models", label: "Models" },
  { to: "/app/admin/flags", label: "Flags" },
  { to: "/app/admin/jobs", label: "Jobs" },
] as const;

function isActive(pathname: string, to: string): boolean {
  const path = pathname.replace(/\/$/, "");
  return to === "/app/admin" ? path === to : path.startsWith(to);
}

/** Admin area (spec 011): platform admins only; anyone else sees "Page not found" (AC1). */
export function AdminLayout() {
  const me = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  if (me.isPending) {
    return (
      <div className="p-4 md:p-8">
        <Loading label="Loading"><ListRowSkeleton /></Loading>
      </div>
    );
  }
  if (me.data?.user.platform_role !== "admin") return <NotFoundPage />;
  return (
    <div className="flex flex-col gap-4 px-4 pt-4 pb-28 sm:pt-6 md:px-8 lg:pb-10">
      <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Admin</h1>
      {/* One scrolling row of sections on phones (no drawer, design principle 9). */}
      <nav aria-label="Admin sections" className="-mx-4 overflow-x-auto px-4 [scrollbar-width:none] md:mx-0 md:px-0">
        <ul className="flex w-max gap-1 rounded-pill border border-border p-1">
          {SECTIONS.map((s) => {
            const active = isActive(pathname, s.to);
            return (
              <li key={s.to}>
                <Link
                  to={s.to}
                  aria-current={active ? "page" : undefined}
                  className={`inline-flex min-h-9 items-center rounded-pill px-3 text-sm ${active ? "bg-primary text-primary-text" : "text-text-secondary hover:text-text"}`}
                >
                  {s.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <Outlet />
    </div>
  );
}
