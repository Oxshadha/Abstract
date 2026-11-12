import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { ArrowLeft, FileText, MessageSquare, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";

import { ErrorBoundary } from "@/components/feedback/ErrorBoundary";
import { getPaper, paperKeys } from "@/features/papers/api";
import { listSummaries, summaryKeys, type Summary } from "@/features/summaries/api";
import { ChatPanel } from "@/features/chat/ChatPanel";
import { SummaryPanel } from "@/features/summaries/SummaryPanel";
import { markOpened } from "@/features/library/api";
import { StarButton } from "@/features/library/PaperActions";
import { CitationProvider } from "@/features/viewer/citations";
import { useCitations } from "@/features/viewer/citation-context";
import { PdfViewer } from "@/features/viewer/PdfViewer";
import { useIsDesktop, useWorkspaceLayout } from "@/features/workspace/layout";
import { PillBar } from "@/components/shell/PillBar";

type PanelId = "paper" | "summary" | "chat";
const MOBILE_TABS = [
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

/** Arriving from a search passage: open the Paper panel at that page and highlight it, once. */
function OpenFromUrl({ paperId }: { paperId: string }) {
  const { page, quote } = useSearch({ from: "/app/papers/$paperId" });
  const citations = useCitations();
  const navigate = useNavigate();
  useEffect(() => {
    if (!page || !citations) return;
    citations.open(page, quote ?? "");
    // Drop the params so a reload or back navigation does not reopen it.
    void navigate({ to: "/app/papers/$paperId", params: { paperId }, search: {}, replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, quote]);
  return null;
}

function PaperPanel({ paperId }: { paperId: string }) {
  return <PdfViewer paperId={paperId} />;
}

function Panel({
  label, children, className = "", width,
}: { label: string; children: ReactNode; className?: string; width?: number }) {
  return (
    <section
      aria-label={label}
      style={width === undefined ? undefined : { flex: `0 0 ${String(width)}%` }}
      className={`min-h-64 min-w-0 overflow-auto rounded-lg border border-border bg-surface p-4 ${className}`}
    >
      <ErrorBoundary name={`the ${label.toLowerCase()} panel`}>{children}</ErrorBoundary>
    </section>
  );
}

/** Drag (or use the arrow keys) to share the width between Paper and Summary (D79). */
function Divider({ split, onChange }: { split: number; onChange: (value: number) => void }) {
  const dragging = useRef(false);
  const move = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return;
    const row = event.currentTarget.parentElement?.getBoundingClientRect();
    if (row && row.width > 0) onChange(((event.clientX - row.left) / row.width) * 100);
  };
  const key = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowLeft") onChange(split - 5);
    if (event.key === "ArrowRight") onChange(split + 5);
  };
  return (
    <div
      role="separator"
      aria-label="Resize Paper and Summary"
      aria-orientation="vertical"
      aria-valuemin={25}
      aria-valuemax={75}
      aria-valuenow={split}
      tabIndex={0}
      onKeyDown={key}
      onPointerDown={(event) => {
        dragging.current = true;
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={move}
      onPointerUp={() => {
        dragging.current = false;
      }}
      className="group flex w-3 shrink-0 cursor-col-resize touch-none items-stretch justify-center"
    >
      <span className="w-px bg-border group-hover:bg-border-strong group-focus-visible:bg-focus" />
    </div>
  );
}

function ToggleButton({ pressed, onClick, disabled, children }: { pressed: boolean; onClick: () => void; disabled?: boolean; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
      title={disabled ? "At least one panel stays open" : undefined}
      className={`inline-flex min-h-11 items-center gap-2 rounded-md border px-3 text-sm disabled:opacity-60 ${
        pressed ? "border-border-strong bg-muted font-medium" : "border-border text-text-secondary hover:bg-muted"
      }`}
    >
      {children}
    </button>
  );
}

/**
 * Workspace (D79, owner direction; supersedes the panel part of D60): Paper and Summary side by
 * side, each can be hidden, the divider resizes them, and chat opens only when asked for. Phones
 * show one panel at a time with a bottom tab bar.
 */
export default function WorkspacePage() {
  const { paperId } = useParams({ from: "/app/papers/$paperId" });
  const { layout, toggle, setChat, setSplit, showPaper } = useWorkspaceLayout();
  const [mobile, setMobile] = useState<PanelId>("summary");
  const paper = useQuery({ queryKey: paperKeys.detail(paperId), queryFn: () => getPaper(paperId) });
  const summaries = useQuery({ queryKey: summaryKeys.forPaper(paperId), queryFn: () => listSummaries(paperId) });
  const headerSummary = useQuery<Summary>({
    queryKey: summaryKeys.detail(summaries.data?.[0]?.id ?? "none"),
    enabled: false, // filled by the Summary panel's live query
  });
  const both = layout.paper && layout.summary;
  const desktop = useIsDesktop();
  // "Recently opened" sort (spec 013 AC3): once per visit, failures are harmless.
  useEffect(() => {
    void markOpened(paperId).catch(() => undefined);
  }, [paperId]);
  // A citation click shows the Paper panel (desktop) or the Paper tab (phones), spec 008 AC4.
  const openPaper = useCallback(() => {
    if (desktop) showPaper();
    else setMobile("paper");
  }, [desktop, showPaper]);

  return (
    <CitationProvider onOpen={openPaper}>
    <OpenFromUrl paperId={paperId} />
    <div className="flex h-full flex-col">
      {/* One line on every screen: back, title (with type and authors beneath), star; the
          panel toggles follow on desktop (owner review: phones wrapped into three lines). */}
      <header className="flex min-w-0 items-center gap-2 px-2 pt-3 sm:gap-3 sm:px-4 sm:pt-4">
        <Link to="/app/library" aria-label="Back to your library" className="inline-flex size-11 shrink-0 items-center justify-center rounded-md hover:bg-muted">
          <ArrowLeft aria-hidden className="size-5" />
        </Link>
        <div className="min-w-0 flex-1">
          <h1 className="truncate font-display text-lg font-bold sm:text-xl md:text-2xl" title={paper.data?.title ?? undefined}>
            {paper.data?.title ?? paper.data?.filename ?? " "}
          </h1>
          <p className="flex min-w-0 items-center gap-2 text-sm text-text-secondary">
            <span className="shrink-0 rounded-sm border border-border px-1.5 text-xs">PDF</span>
            <span className="truncate">{byline(headerSummary.data)}</span>
          </p>
        </div>
        {paper.data && <StarButton paper={paper.data} />}
        {desktop && (
        <div role="toolbar" aria-label="Panels" className="flex shrink-0 items-center gap-2">
          <ToggleButton pressed={layout.paper} disabled={layout.paper && !layout.summary} onClick={() => { toggle("paper"); }}>
            <FileText aria-hidden className="size-4" />
            Paper
          </ToggleButton>
          <ToggleButton pressed={layout.summary} disabled={layout.summary && !layout.paper} onClick={() => { toggle("summary"); }}>
            <Sparkles aria-hidden className="size-4" />
            Summary
          </ToggleButton>
          <ToggleButton pressed={layout.chat} onClick={() => { setChat(!layout.chat); }}>
            <MessageSquare aria-hidden className="size-4" />
            Ask Abstract
          </ToggleButton>
        </div>
        )}
      </header>

      {/* Desktop: resizable Paper | Summary, chat as a side panel on demand. */}
      {desktop ? (
      <div className="flex min-h-0 flex-1 gap-4 p-4" data-paper-id={paperId}>
        <div className="flex min-w-0 flex-1">
          {layout.paper && (
            <Panel label="Paper" className={both ? "" : "flex-1"} width={both ? layout.split : undefined}>
              <PaperPanel paperId={paperId} />
            </Panel>
          )}
          {both && <Divider split={layout.split} onChange={setSplit} />}
          {layout.summary && (
            <Panel label="Summary" className="flex-1">
              <SummaryPanel paperId={paperId} />
            </Panel>
          )}
        </div>
        {layout.chat && (
          <Panel label="Ask Abstract" className="w-96 shrink-0">
            <ChatPanel paperId={paperId} onClose={() => { setChat(false); }} />
          </Panel>
        )}
      </div>

      ) : (
      <>
      {/* Phones and tablets: one panel at a time (D60). */}
      <div className="flex-1 p-4 pb-24">
        {/* Hidden, not unmounted: a citation tapped mid-answer switches to Paper without
            cancelling the streaming answer, and the viewer keeps its place. */}
        <div hidden={mobile !== "paper"}><Panel label="Paper"><PaperPanel paperId={paperId} /></Panel></div>
        <div hidden={mobile !== "summary"}><Panel label="Summary"><SummaryPanel paperId={paperId} /></Panel></div>
        <div hidden={mobile !== "chat"}><Panel label="Ask Abstract"><ChatPanel paperId={paperId} /></Panel></div>
      </div>
      <PillBar
        label="Workspace panels"
        hideFrom="lg"
        items={MOBILE_TABS.map(({ id, label, Icon }) => ({
          key: id,
          label,
          icon: <Icon aria-hidden className="size-5" />,
          active: mobile === id,
          onSelect: () => { setMobile(id); },
        }))}
      />
      </>
      )}
    </div>
    </CitationProvider>
  );
}
