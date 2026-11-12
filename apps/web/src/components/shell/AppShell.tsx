import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { Bell, Search } from "lucide-react";
import { useEffect, useState } from "react";

import { ErrorBoundary } from "@/components/feedback/ErrorBoundary";
import { OfflineBanner } from "@/components/feedback/offline";
import { SearchDialog } from "@/features/library/SearchDialog";
import { useOpenCollection } from "@/features/library/useOpenCollection";

import { LogoMark } from "@/components/brand/Logo";

import { NAV_ITEMS } from "./navigation";
import { PillBar } from "./PillBar";
import { Sidebar } from "./Sidebar";
import { UserMenu } from "./UserMenu";

/** App shell from the Library mockup. Phones: brand in the top bar, floating pill navigation (D86). */
export function AppShell() {
  const [searchOpen, setSearchOpen] = useState(false);
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  // The Workspace has its own Paper / Summary / Chat bar on phones.
  const inWorkspace = /^\/app\/papers\/[^/]+$/.test(pathname);
  // Home scrolls its own list under the pill bar on phones, so the page reserves no space for it.
  const ownsScroll = inWorkspace || pathname === "/app/home";
  // Pages that keep their header and tools fixed and scroll only their list or panels.
  const fixedPage = inWorkspace || pathname === "/app/library";
  const collection = useOpenCollection();
  const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.userAgent);
  const shortcut = isMac ? "Cmd+K" : "Ctrl+K";

  // Ctrl+K or Cmd+K opens search from anywhere (spec 013 AC8); no badge on screen (D82).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); };
  }, []);

  return (
    <div className="flex h-dvh overflow-hidden bg-bg text-text">
      <aside className="hidden h-dvh w-64 shrink-0 flex-col border-r border-border md:flex">
        <Sidebar />
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <OfflineBanner />
        <header className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-3">
          {/* Phones: the brand where the menu button was; navigation is the pill bar (D86). */}
          <Link to="/app/home" aria-label="abstract. home" className="inline-flex min-h-11 items-center md:hidden">
            <LogoMark className="size-7" />
            <span className="ml-1.5 font-display text-xl font-bold tracking-tight">abstract.</span>
          </Link>
          <button
            type="button"
            title={`Search (${shortcut})`}
            aria-haspopup="dialog"
            onClick={() => { setSearchOpen(true); }}
            className="hidden min-h-11 min-w-0 flex-1 items-center gap-2 rounded-lg border border-border bg-surface px-3 text-left text-text-secondary sm:flex md:max-w-xl"
          >
            <Search aria-hidden className="size-4 shrink-0" />
            <span className="truncate">Search papers, collections, or keywords</span>
          </button>
          {/* Phones: an icon that opens a full-screen search instead of a squeezed field. */}
          <button
            type="button"
            aria-label="Search"
            aria-haspopup="dialog"
            onClick={() => { setSearchOpen(true); }}
            className="ml-auto inline-flex size-11 items-center justify-center rounded-md hover:bg-muted sm:hidden"
          >
            <Search aria-hidden className="size-5" />
          </button>
          <div className="flex items-center gap-1 sm:ml-auto">
            <button
              type="button"
              aria-label="Notifications"
              className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted"
            >
              <Bell aria-hidden className="size-5" />
            </button>
            <UserMenu />
          </div>
        </header>
        <SearchDialog open={searchOpen} onClose={() => { setSearchOpen(false); }} collection={collection ?? null} />
        {/* The page fits the window; only this area (or a panel inside it) scrolls (design principle 5). */}
        <main id="main" className={`min-h-0 min-w-0 flex-1 ${fixedPage ? "overflow-hidden" : ownsScroll ? "overflow-hidden md:overflow-y-auto" : "overflow-y-auto pb-24 md:pb-0"}`}>
          <ErrorBoundary name="this page">
            <Outlet />
          </ErrorBoundary>
        </main>
        {!inWorkspace && (
          <PillBar
            label="Navigation"
            items={NAV_ITEMS.map(({ to, label, Icon }) => ({
              key: to,
              label,
              icon: <Icon aria-hidden className="size-5" />,
              active: pathname.startsWith(to),
              render: (props) => <Link to={to} {...props} aria-current={pathname.startsWith(to) ? "page" : undefined} />,
            }))}
          />
        )}
      </div>
    </div>
  );
}
