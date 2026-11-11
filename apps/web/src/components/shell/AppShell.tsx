import { Outlet } from "@tanstack/react-router";
import { Bell, Menu, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ErrorBoundary } from "@/components/feedback/ErrorBoundary";

import { Sidebar } from "./Sidebar";
import { UserMenu } from "./UserMenu";

/** App shell from the Library mockup; sidebar becomes a drawer below 768 px (AC6, D60). */
export function AppShell() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);

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
            className="flex min-h-11 min-w-0 flex-1 items-center gap-2 rounded-lg border border-border bg-surface px-3 text-left text-text-secondary md:max-w-xl"
            aria-label="Search papers, collections, or keywords"
          >
            <Search aria-hidden className="size-4 shrink-0" />
            <span className="truncate">Search papers, collections, or keywords</span>
            <kbd className="ml-auto hidden rounded-sm bg-muted px-1.5 text-xs sm:inline">⌘K</kbd>
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
        <main id="main" className="min-w-0 flex-1">
          <ErrorBoundary name="this page">
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
