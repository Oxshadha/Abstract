import { useParams } from "@tanstack/react-router";
import { FileText, MessageSquare, Sparkles } from "lucide-react";
import { useState } from "react";

import { ErrorBoundary } from "@/components/feedback/ErrorBoundary";

const PANELS = [
  { id: "paper", label: "Paper", Icon: FileText },
  { id: "summary", label: "Summary", Icon: Sparkles },
  { id: "chat", label: "Chat", Icon: MessageSquare },
] as const;

/** Workspace layout (D60): three panels on desktop, one panel with a bottom tab bar on phones. */
export default function WorkspacePage() {
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
            <ErrorBoundary name={`the ${label.toLowerCase()} panel`}>
              <h2 className="font-display text-lg font-bold">{label === "Chat" ? "Ask Abstract" : label}</h2>
            </ErrorBoundary>
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
