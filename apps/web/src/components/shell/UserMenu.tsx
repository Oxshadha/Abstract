import { useQuery } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { fetchMe } from "@/api/me";
import { useAuthState } from "@/auth/state";
import { ThemeToggle } from "@/theme/ThemeToggle";

function initials(name: string | null | undefined): string {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  return (parts.slice(0, 2).map((p) => p[0]).join("") || "?").toUpperCase();
}

/** Avatar menu: who you are, theme, sign out (spec 003 AC6). */
export function UserMenu() {
  const auth = useAuthState();
  const me = useQuery({ queryKey: ["me"], queryFn: fetchMe, enabled: auth.status === "signed-in" });
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const onClick = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  const name = me.data?.user.display_name ?? me.data?.user.email ?? "Account";
  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`${initials(me.data?.user.display_name ?? me.data?.user.email)}, account menu for ${name}`}
        onClick={() => {
          setOpen((v) => !v);
        }}
        className="inline-flex size-11 items-center justify-center rounded-pill bg-muted font-medium text-text"
      >
        {/* The accessible name starts with the visible initials (WCAG 2.5.3). */}
        {initials(me.data?.user.display_name ?? me.data?.user.email)}
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-20 mt-2 w-72 rounded-lg border border-border bg-surface p-3 shadow-overlay">
          <p className="truncate px-1 font-medium" title={name}>
            {name}
          </p>
          {me.data?.org && (
            <p className="truncate px-1 text-sm text-text-secondary" title={me.data.org.name}>
              {me.data.org.name}
            </p>
          )}
          <div className="py-3">
            <ThemeToggle />
          </div>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              auth.signOut();
            }}
            className="flex min-h-11 w-full items-center gap-2 rounded-md px-2 text-left text-error hover:bg-muted"
          >
            <LogOut aria-hidden className="size-4" />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
