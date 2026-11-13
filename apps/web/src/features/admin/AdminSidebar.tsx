import { useQuery } from "@tanstack/react-query";
import { Link, useRouterState } from "@tanstack/react-router";
import { ArrowLeft, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useLayoutEffect, useRef, useState } from "react";

import { Logo, LogoMark } from "@/components/brand/Logo";

import { adminKeys, getOverview } from "./api";
import { SECTION_GROUPS, isActive } from "./sections";

const KEY = "abstract.admin.sidebar";

function savedCollapsed(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "collapsed";
  } catch {
    return false;
  }
}

function saveCollapsed(collapsed: boolean) {
  try {
    window.localStorage.setItem(KEY, collapsed ? "collapsed" : "open");
  } catch {
    // private mode: the sidebar opens expanded next visit
  }
}

/** Labels fade with the width; collapsed, the icon keeps the name as a tooltip and for screen readers. */
function Label({ hidden, children }: { hidden: boolean; children: string }) {
  return (
    <span className={`truncate transition-opacity duration-150 motion-reduce:transition-none ${hidden ? "sr-only opacity-0" : "opacity-100"}`}>
      {children}
    </span>
  );
}

/**
 * Admin sidebar on desktop (spec 018 AC1, AC2; D97). Adapted from the owner's reference: groups,
 * an active pill that glides between items, and a collapse to an icon rail that the device
 * remembers. No animation library: CSS transitions, off with reduced motion.
 */
export function AdminSidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const [collapsed, setCollapsed] = useState(savedCollapsed);
  const overview = useQuery({ queryKey: adminKeys.overview, queryFn: getOverview, refetchInterval: 30_000 });
  const failed = overview.data?.jobs.failed_24h ?? 0;

  // The pill is one element moved to the active link, so it glides instead of jumping.
  const listRef = useRef<HTMLDivElement>(null);
  const [pill, setPill] = useState<{ top: number; height: number } | null>(null);
  useLayoutEffect(() => {
    const active = listRef.current?.querySelector<HTMLElement>('[aria-current="page"]');
    setPill(active ? { top: active.offsetTop, height: active.offsetHeight } : null);
  }, [pathname, collapsed]);

  const toggle = () => {
    setCollapsed((c) => {
      saveCollapsed(!c);
      return !c;
    });
  };

  return (
    <aside
      aria-label="Admin"
      data-collapsed={collapsed ? "true" : "false"}
      className={`hidden h-dvh shrink-0 flex-col border-r border-border transition-[width] duration-[240ms] ease-out motion-reduce:transition-none md:flex ${collapsed ? "w-[72px]" : "w-64"}`}
    >
      <div className={`flex h-[68px] shrink-0 items-center ${collapsed ? "justify-center" : "px-6"}`}>
        {collapsed ? (
          <button type="button" onClick={toggle} aria-label="Expand sidebar" title="Expand sidebar" className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted">
            <LogoMark className="size-7" />
          </button>
        ) : (
          <Link to="/app/home" aria-label="abstract. home">
            <Logo />
          </Link>
        )}
      </div>

      <nav aria-label="Admin sections" className="flex min-h-0 flex-1 flex-col overflow-y-auto overflow-x-hidden px-3 [scrollbar-width:none]">
        <Link
          to="/app/home"
          title={collapsed ? "Back to app" : undefined}
          className={`flex min-h-11 items-center gap-3 rounded-md text-text-secondary hover:bg-muted hover:text-text ${collapsed ? "justify-center" : "px-3"}`}
        >
          <ArrowLeft aria-hidden className="size-5 shrink-0" />
          <Label hidden={collapsed}>Back to app</Label>
        </Link>

        <div ref={listRef} className="relative mt-4 flex flex-col gap-4">
          {pill && (
            <span
              aria-hidden
              className="pointer-events-none absolute inset-x-0 rounded-md bg-muted transition-[top,height] duration-[240ms] ease-out motion-reduce:transition-none"
              style={{ top: pill.top, height: pill.height }}
            />
          )}
          {SECTION_GROUPS.map((group) => (
            <div key={group.label} role="group" aria-label={group.label}>
              <p
                aria-hidden
                className={`flex h-7 items-end px-3 pb-1.5 text-xs font-medium uppercase tracking-wider text-text-secondary transition-opacity duration-150 motion-reduce:transition-none ${collapsed ? "opacity-0" : "opacity-100"}`}
              >
                {group.label}
              </p>
              <ul className="flex flex-col gap-1">
                {group.items.map(({ to, label, Icon }) => {
                  const active = isActive(pathname, to);
                  const badge = to === "/app/admin/jobs" && failed > 0 ? failed : null;
                  return (
                    <li key={to}>
                      <Link
                        to={to}
                        aria-current={active ? "page" : undefined}
                        title={collapsed ? (badge ? `${label} ${String(badge)} failed` : label) : undefined}
                        className={`relative flex min-h-11 items-center gap-3 rounded-md ${collapsed ? "justify-center" : "px-3"} ${active ? "font-medium text-text" : "text-text-secondary hover:bg-muted/60 hover:text-text"}`}
                      >
                        <Icon aria-hidden className="relative size-5 shrink-0" />
                        <Label hidden={collapsed}>{label}</Label>
                        {badge !== null && (
                          <>
                            {" "}
                            <span
                              className={`rounded-pill bg-primary px-1.5 text-xs font-medium leading-5 text-primary-text ${collapsed ? "absolute right-1 top-1" : "relative ml-auto"}`}
                            >
                              {badge}
                              {" "}
                              <span className="sr-only">failed</span>
                            </span>
                          </>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </nav>

      <div className={`shrink-0 border-t border-border p-3 ${collapsed ? "flex justify-center" : ""}`}>
        <button
          type="button"
          onClick={toggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          title={collapsed ? "Expand sidebar" : undefined}
          className={`flex min-h-11 items-center gap-3 rounded-md text-text-secondary hover:bg-muted hover:text-text ${collapsed ? "w-11 justify-center" : "w-full px-3"}`}
        >
          {collapsed ? <PanelLeftOpen aria-hidden className="size-5" /> : <PanelLeftClose aria-hidden className="size-5" />}
          <Label hidden={collapsed}>Collapse</Label>
        </button>
      </div>
    </aside>
  );
}
