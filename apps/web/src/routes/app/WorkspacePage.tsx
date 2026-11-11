import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { ArrowLeft, FileText, MessageSquare, Sparkles } from "lucide-react";
import { useState } from "react";

import { ErrorBoundary } from "@/components/feedback/ErrorBoundary";
import { getPaper, paperKeys } from "@/features/papers/api";
import { listSummaries, summaryKeys, type Summary } from "@/features/summaries/api";
import { SummaryPanel } from "@/features/summaries/SummaryPanel";

const PANELS = [
  { id: "paper", label: "Paper", Icon: FileText },
  { id: "summary", label: "Summary", Icon: Sparkles },
  { id: "chat", label: "Chat", Icon: MessageSquare },
] as const;

function byline(summary: Summary | undefined): string {
  if (!summary) return "";
  const first = summary.authors[0];
  const authors = first ? (summary.authors.length > 1 ? `${first.split(" ").pop() ?? first} et al.` : first) : "";
  return [authors, summary.year ? String(summary.year) : ""].filter(Boolean).join(" · ");
}

/** Workspace (D60, mockup): three panels on desktop, one panel with a bottom tab bar on phones. */
export default function WorkspacePage() {
  const { paperId } = useParams({ from: "/app/papers/$paperId" });
  const [active, setActive] = useState<(typeof PANELS)[number]["id"]>("summary");
  const paper = useQuery({ queryKey: paperKeys.detail(paperId), queryFn: () => getPaper(paperId) });
  const summaries = useQuery({ queryKey: summaryKeys.forPaper(paperId), queryFn: () => listSummaries(paperId) });
  const firstSummaryId = summaries.data?.[0]?.id;
  const headerSummary = useQuery<Summary>({
    queryKey: summaryKeys.detail(firstSummaryId ?? "none"),
    enabled: false, // filled by the Summary panel's live query
  });

  return (
    <div className="flex h-full flex-col">
      <header className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 px-4 pt-4">
        <Link to="/app/library" aria-label="Back to your library" className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted">
          <ArrowLeft aria-hidden className="size-5" />
        </Link>
        <h1 className="min-w-0 truncate font-display text-xl font-bold md:text-2xl" title={paper.data?.title ?? undefined}>
          {paper.data?.title ?? paper.data?.filename ?? " "}
        </h1>
        <span className="rounded-sm border border-border px-1.5 text-xs text-text-secondary">PDF</span>
        <span className="text-sm text-text-secondary">{byline(headerSummary.data)}</span>
      </header>
      <div className="grid flex-1 gap-4 p-4 pb-20 lg:grid-cols-3 lg:pb-4" data-paper-id={paperId}>
        {PANELS.map(({ id, label }) => (
          <section
            key={id}
            aria-label={label}
            className={`${active === id ? "block" : "hidden"} min-h-64 rounded-lg border border-border bg-surface p-4 lg:block`}
          >
            <ErrorBoundary name={`the ${label.toLowerCase()} panel`}>
              {id === "summary" ? (
                <SummaryPanel paperId={paperId} />
              ) : (
                <h2 className="font-display text-lg font-bold">{label === "Chat" ? "Ask Abstract" : label}</h2>
              )}
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
