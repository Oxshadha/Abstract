import { Outlet } from "@tanstack/react-router";
import { Bell, Menu, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ErrorBoundary } from "@/components/feedback/ErrorBoundary";
import { OfflineBanner } from "@/components/feedback/offline";
import { SearchDialog } from "@/features/library/SearchDialog";
import { useOpenCollection } from "@/features/library/useOpenCollection";

import { Sidebar } from "./Sidebar";
import { UserMenu } from "./UserMenu";

/** App shell from the Library mockup; sidebar becomes a drawer below 768 px (AC6, D60). */
export function AppShell() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const [searchOpen, setSearchOpen] = useState(false);
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

  useEffect(() => {
    if (!drawerOpen) return;
    const trigger = menuButton.current;
    closeButton.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      trigger?.focus(); // return focus to the trigger
    };
  }, [drawerOpen]);

  return (
    <div className="flex min-h-dvh bg-bg text-text">
      <aside className="hidden w-64 shrink-0 border-r border-border md:block">
        <Sidebar />
      </aside>

      {drawerOpen && (
        <div className="fixed inset-0 z-30 md:hidden">
          <div
            className="absolute inset-0 bg-text/40 motion-safe:animate-in"
            aria-hidden
            onClick={() => {
              setDrawerOpen(false);
            }}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            className="absolute inset-y-0 left-0 w-72 max-w-[85vw] bg-surface shadow-overlay"
          >
            <button
              ref={closeButton}
              type="button"
              aria-label="Close navigation"
              onClick={() => {
                setDrawerOpen(false);
              }}
              className="absolute top-3 right-3 inline-flex size-11 items-center justify-center rounded-md hover:bg-muted"
            >
              <X aria-hidden className="size-5" />
            </button>
            <Sidebar
              onNavigate={() => {
                setDrawerOpen(false);
              }}
            />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <OfflineBanner />
        <header className="flex items-center gap-2 border-b border-border px-4 py-3">
          <button
            ref={menuButton}
            type="button"
            aria-label="Open navigation"
            aria-expanded={drawerOpen}
            onClick={() => {
              setDrawerOpen(true);
            }}
            className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted md:hidden"
          >
            <Menu aria-hidden className="size-5" />
          </button>
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
            className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted sm:hidden"
          >
            <Search aria-hidden className="size-5" />
          </button>
          <div className="ml-auto flex items-center gap-1">
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
        <main id="main" className="min-w-0 flex-1">
          <ErrorBoundary name="this page">
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
