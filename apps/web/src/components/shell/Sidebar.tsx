import { Link } from "@tanstack/react-router";

import { Logo } from "@/components/brand/Logo";

import { NAV_ITEMS } from "./navigation";

/** Sidebar from the Library mockup (spec 003 AC6). */
export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Main" className="flex h-full flex-col gap-6 p-4">
      <Link to="/app/library" onClick={onNavigate} className="px-2">
        <Logo />
      </Link>
      <ul className="flex flex-col gap-1">
        {NAV_ITEMS.map(({ to, label, Icon }) => (
          <li key={to}>
            <Link
              to={to}
              onClick={onNavigate}
              className="flex min-h-11 items-center gap-3 rounded-md px-3 text-text-secondary hover:bg-muted hover:text-text"
              activeProps={{ className: "bg-muted font-medium text-text", "aria-current": "page" }}
            >
              <Icon aria-hidden className="size-5" />
              {label}
            </Link>
          </li>
        ))}
      </ul>
      <section aria-labelledby="recent-heading" className="border-t border-border pt-4">
        <h2 id="recent-heading" className="px-3 text-xs font-medium tracking-wide text-text-secondary uppercase">
          Recent
        </h2>
        <p className="px-3 pt-2 text-sm text-text-secondary">Papers you open will show up here.</p>
      </section>
    </nav>
  );
}
