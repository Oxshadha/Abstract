import { useParams } from "@tanstack/react-router";
import { FileText, MessageSquare, Sparkles } from "lucide-react";
import { useState } from "react";

function PageHeader({ title, description }: { title: string; description: string }) {
  return (
    <header className="px-4 pt-6 pb-4 md:px-8">
      <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
      <p className="mt-1 text-text-secondary">{description}</p>
    </header>
  );
}

export function LibraryPage() {
  return <PageHeader title="Your Library" description="Upload, organize, summarize, and explore your research papers." />;
}

export function CollectionsPage() {
  return <PageHeader title="Collections" description="Group related papers to keep your research organized." />;
}

export function TemplatesPage() {
  return <PageHeader title="Templates" description="Choose or design how summaries are structured." />;
}

export function SettingsPage() {
  return <PageHeader title="Settings" description="Account, appearance, and workspace preferences." />;
}

const PANELS = [
  { id: "paper", label: "Paper", Icon: FileText },
  { id: "summary", label: "Summary", Icon: Sparkles },
  { id: "chat", label: "Chat", Icon: MessageSquare },
] as const;

/** Workspace layout (D60): three panels on desktop, one panel with a bottom tab bar on phones. */
export function WorkspacePage() {
  const { paperId } = useParams({ from: "/app/papers/$paperId" });
  const [active, setActive] = useState<(typeof PANELS)[number]["id"]>("summary");
  return (
    <div className="flex h-full flex-col">
      <div className="grid flex-1 gap-4 p-4 pb-20 lg:grid-cols-3 lg:pb-4" data-paper-id={paperId}>
        {PANELS.map(({ id, label }) => (
          <section
            key={id}
            aria-label={label}
            className={`${active === id ? "block" : "hidden"} min-h-64 rounded-lg border border-border bg-surface p-4 lg:block`}
          >
            <h2 className="font-display text-lg font-bold">{label === "Chat" ? "Ask Abstract" : label}</h2>
          </section>
        ))}
      </div>
      <nav
        aria-label="Workspace panels"
        className="fixed inset-x-0 bottom-0 grid grid-cols-3 border-t border-border bg-surface lg:hidden"
      >
        {PANELS.map(({ id, label, Icon }) => (
          <button
            key={id}
            type="button"
            aria-pressed={active === id}
            onClick={() => {
              setActive(id);
            }}
            className={`flex min-h-14 flex-col items-center justify-center gap-0.5 text-xs ${active === id ? "font-medium text-text" : "text-text-secondary"}`}
          >
            <Icon aria-hidden className="size-5" />
            {label}
          </button>
        ))}
      </nav>
    </div>
  );
}

export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-md px-4 py-16 text-center">
      <h1 className="text-2xl font-bold">Page not found</h1>
      <p className="mt-2 text-text-secondary">The page you are looking for does not exist or has moved.</p>
      <a href="/app/library" className="mt-6 inline-flex min-h-11 items-center rounded-pill bg-primary px-5 text-primary-text">
        Go to your library
      </a>
    </div>
  );
}
