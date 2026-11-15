import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { ArrowLeft, FileText, LayoutPanelLeft, MessageSquare, NotebookPen, Quote, Sparkles } from "lucide-react";
import { Suspense, lazy, useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";

import { ErrorBoundary } from "@/components/feedback/ErrorBoundary";
import { getPaper, paperKeys } from "@/features/papers/api";
import { listSummaries, summaryKeys, type Summary } from "@/features/summaries/api";
import { ChatPanel } from "@/features/chat/ChatPanel";
import { SummaryPanel } from "@/features/summaries/SummaryPanel";
import { markOpened } from "@/features/library/api";
import { StarButton } from "@/features/library/PaperActions";
import { CitationProvider } from "@/features/viewer/citations";
import { useCitations } from "@/features/viewer/citation-context";
import { FiguresPanel } from "@/features/viewer/FiguresPanel";
import { PdfViewer } from "@/features/viewer/PdfViewer";
import { MAX_CHAT, MIN_CHAT, useIsDesktop, useWorkspaceLayout } from "@/features/workspace/layout";
import { PillBar } from "@/components/shell/PillBar";
import { useFlag } from "@/features/flags/api";
import { SummaryCardSkeleton } from "@/components/feedback/Skeleton";
import { ReferencesPanel } from "@/features/references/ReferencesPanel";
import { useStopReadingOnLeave } from "@/features/voice/hooks";

// The editor (TipTap) loads only when Notes is opened, keeping the Workspace light.
const NotesPanel = lazy(() => import("@/features/notes/NotesPanel").then((m) => ({ default: m.NotesPanel })));

function Notes({ paperId }: { paperId: string }) {
  return (
    <Suspense fallback={<SummaryCardSkeleton />}>
      <NotesPanel paperId={paperId} />
    </Suspense>
  );
}

type PanelId = "paper" | "summary" | "chat" | "notes" | "references";
// Phones (D95): Notes and References join the pill, five icons; each follows its flag.
const MOBILE_TABS = [
  { id: "paper", label: "Paper", Icon: FileText },
  { id: "summary", label: "Summary", Icon: Sparkles },
  { id: "chat", label: "Chat", Icon: MessageSquare },
  { id: "notes", label: "Notes", Icon: NotebookPen },
  { id: "references", label: "References", Icon: Quote },
] as const;

type TabId = "workspace" | "notes" | "references";
// Desktop: tabs under the paper title (mockup).
const TABS = [
  { id: "workspace", label: "Workspace", Icon: LayoutPanelLeft },
  { id: "notes", label: "Notes", Icon: NotebookPen },
  { id: "references", label: "References", Icon: Quote },
] as const;

/** Workspace, Notes and References under the title on desktop (spec 014, mockup). */
function Tabs({ tabs, current, onSelect }: { tabs: readonly (typeof TABS)[number][]; current: TabId; onSelect: (id: TabId) => void }) {
  return (
    <div role="tablist" aria-label="Paper views" className="flex gap-1 border-b border-border px-4">
      {tabs.map(({ id, label, Icon }) => (
        <button
          key={id}
          type="button"
          role="tab"
          aria-selected={current === id}
          onClick={() => { onSelect(id); }}
          onKeyDown={(event) => {
            const i = tabs.findIndex((t) => t.id === id);
            const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
            if (!step) return;
            const next = tabs[(i + step + tabs.length) % tabs.length];
            if (next) onSelect(next.id);
          }}
          tabIndex={current === id ? 0 : -1}
          className={`-mb-px inline-flex min-h-11 items-center gap-2 border-b-2 px-3 text-sm ${
            current === id ? "border-text font-medium text-text" : "border-transparent text-text-secondary hover:text-text"
          }`}
        >
          <Icon aria-hidden className="size-4" />
          {label}
        </button>
      ))}
    </div>
  );
}

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

/** Paper panel: the pages, or the paper's tables and figures (spec 009 AC5, D85). */
function PaperPanel({ paperId }: { paperId: string }) {
  const [view, setView] = useState<"pages" | "figures">("pages");
  const citations = useCitations();
  const figures = useFlag("figures"); // spec 011 AC7
  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      {figures && (
      <div role="group" aria-label="Paper view" className="flex w-fit rounded-pill border border-border p-1">
        {(["pages", "figures"] as const).map((v) => (
          <button
            key={v}
            type="button"
            aria-pressed={view === v}
            onClick={() => { setView(v); }}
            className={`min-h-9 rounded-pill px-3 text-sm ${view === v ? "bg-primary text-primary-text" : "text-text-secondary hover:text-text"}`}
          >
            {v === "pages" ? "Pages" : "Figures & tables"}
          </button>
        ))}
      </div>
      )}
      {/* Both stay mounted: switching back keeps the viewer's place. */}
      {/* Phones and tablets: the viewer gets the screen height under the bars, so it scrolls
          itself and can jump to a citation or table (the page would otherwise grow instead). */}
      <div hidden={view !== "pages"} className="min-h-0 flex-1">
        <PdfViewer paperId={paperId} />
      </div>
      {figures && view === "figures" && (
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain max-lg:pb-28">
        <FiguresPanel
          paperId={paperId}
          onShow={(page, box, label) => {
            setView("pages");
            citations?.openBox(page, box, label);
          }}
        />
        </div>
      )}
    </div>
  );
}

function Panel({
  label, children, className = "", width, pixels, bare,
}: { label: string; children: ReactNode; className?: string; width?: number; pixels?: number; bare?: "scroll" | "fill" | "under" }) {
  // Phones: no card frame, the panel uses the whole screen and the pill bar floats over it
  // ("scroll" pages through its content; "fill" hands the height to a viewer or chat).
  const frame = bare
    ? `h-full min-w-0 ${
        bare === "scroll"
          ? "overflow-y-auto px-4 pt-2 pb-28"
          : bare === "fill"
            ? "flex flex-col overflow-hidden px-2 pt-2 pb-24"
            : "flex flex-col overflow-hidden px-2 pt-2" // the viewer scrolls under the pill itself
      }`
    : "flex min-h-64 min-w-0 flex-col overflow-hidden rounded-lg border border-border bg-surface p-4"; // content scrolls inside
  return (
    <section
      aria-label={label}
      style={pixels !== undefined ? { width: pixels } : width === undefined ? undefined : { flex: `0 0 ${String(width)}%` }}
      className={`${frame} ${className}`}
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

/** Drag (or use the arrow keys) to widen or narrow the chat panel; remembered per device. */
function ChatDivider({ width, onChange }: { width: number; onChange: (value: number) => void }) {
  const dragging = useRef(false);
  const move = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return;
    const chat = event.currentTarget.nextElementSibling?.getBoundingClientRect();
    if (chat) onChange(chat.right - event.clientX);
  };
  const key = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowLeft") onChange(width + 32);
    if (event.key === "ArrowRight") onChange(width - 32);
  };
  return (
    <div
      role="separator"
      aria-label="Resize Ask Abstract"
      aria-orientation="vertical"
      aria-valuemin={MIN_CHAT}
      aria-valuemax={MAX_CHAT}
      aria-valuenow={width}
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
      className="group -mx-3 flex w-3 shrink-0 cursor-col-resize touch-none items-stretch justify-center"
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
  useStopReadingOnLeave(paperId); // spec 020 AC5
  const { layout, toggle, setChat, setSplit, setChatWidth, showPaper } = useWorkspaceLayout();
  const [mobile, setMobile] = useState<PanelId>("summary");
  const [tab, setTab] = useState<TabId>("workspace");
  const notesOn = useFlag("notes"); // spec 014 AC8
  const referencesOn = useFlag("references");
  const shown = (id: string) => (id === "notes" ? notesOn : id === "references" ? referencesOn : true);
  const tabs = TABS.filter((t) => shown(t.id));
  const view: TabId = shown(tab) ? tab : "workspace"; // a flag turned off falls back
  const phone: PanelId = shown(mobile) ? mobile : "summary";
  const paper = useQuery({ queryKey: paperKeys.detail(paperId), queryFn: () => getPaper(paperId) });
  const summaries = useQuery({ queryKey: summaryKeys.forPaper(paperId), queryFn: () => listSummaries(paperId) });
  const headerSummary = useQuery<Summary>({
    queryKey: summaryKeys.detail(summaries.data?.[0]?.id ?? "none"),
    enabled: false, // filled by the Summary panel's live query
  });
  // Notes sit beside the paper, so a source opens next to the note (D95).
  const paperShown = view === "notes" || layout.paper;
  const both = view === "notes" || (layout.paper && layout.summary);
  const desktop = useIsDesktop();
  // "Recently opened" sort (spec 013 AC3): once per visit, failures are harmless.
  useEffect(() => {
    void markOpened(paperId).catch(() => undefined);
  }, [paperId]);
  // A citation click shows the Paper panel (desktop) or the Paper tab (phones), spec 008 AC4.
  // "Ask about this region" brings up the chat: the side panel on desktop, the Chat tab on phones.
  const openChat = useCallback(() => {
    if (desktop) setChat(true);
    else setMobile("chat");
  }, [desktop, setChat]);
  const openPaper = useCallback(() => {
    if (desktop) showPaper();
    else setMobile("paper");
  }, [desktop, showPaper]);

  return (
    <CitationProvider onOpen={openPaper} onAskRegion={openChat}>
    <OpenFromUrl paperId={paperId} />
    {/* Desktop: the Workspace fills the screen under the top bar and each panel scrolls on its
        own, like an editor (D79); phones scroll the page. */}
    <div className="flex h-full min-h-0 flex-col">
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
        {desktop && view === "workspace" && (
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

      {desktop && tabs.length > 1 && <Tabs tabs={tabs} current={view} onSelect={setTab} />}

      {/* Desktop: resizable Paper | Summary (or Notes), chat as a side panel on demand. The Paper
          panel keeps its place in the tree across Workspace and Notes, so the viewer stays put. */}
      {desktop ? (
      <div className="flex min-h-0 flex-1 gap-4 p-4" data-paper-id={paperId}>
        {view === "references" ? (
          <Panel label="References" className="flex-1">
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              <ReferencesPanel paperId={paperId} />
            </div>
          </Panel>
        ) : (
        <>
        <div className="flex min-w-0 flex-1">
          {paperShown && (
            <Panel label="Paper" className={both ? "" : "flex-1"} width={both ? layout.split : undefined}>
              <PaperPanel paperId={paperId} />
            </Panel>
          )}
          {both && <Divider split={layout.split} onChange={setSplit} />}
          {view === "notes" ? (
            <Panel label="Notes" className="flex-1">
              <Notes paperId={paperId} />
            </Panel>
          ) : (
            layout.summary && (
              <Panel label="Summary" className="flex-1">
                <SummaryPanel paperId={paperId} />
              </Panel>
            )
          )}
        </div>
        {view === "workspace" && layout.chat && (
          <>
            <ChatDivider width={layout.chatWidth} onChange={setChatWidth} />
            <Panel label="Ask Abstract" className="shrink-0" pixels={layout.chatWidth}>
              <ChatPanel paperId={paperId} onClose={() => { setChat(false); }} />
            </Panel>
          </>
        )}
        </>
        )}
      </div>

      ) : (
      <>
      {/* Phones and tablets: one panel at a time (D60). */}
      <div className="relative min-h-0 flex-1">
        {/* Hidden, not unmounted: a citation tapped mid-answer switches to Paper without
            cancelling the streaming answer, and the viewer keeps its place. */}
        <div hidden={phone !== "paper"} className="h-full"><Panel label="Paper" bare="under"><PaperPanel paperId={paperId} /></Panel></div>
        <div hidden={phone !== "summary"} className="h-full"><Panel label="Summary" bare="under"><SummaryPanel paperId={paperId} /></Panel></div>
        <div hidden={phone !== "chat"} className="h-full"><Panel label="Ask Abstract" bare="fill"><ChatPanel paperId={paperId} /></Panel></div>
        {/* Mounted only while shown: notes save on leaving, references poll only when seen. */}
        {phone === "notes" && <div className="h-full"><Panel label="Notes" bare="fill"><Notes paperId={paperId} /></Panel></div>}
        {phone === "references" && <div className="h-full"><Panel label="References" bare="scroll"><ReferencesPanel paperId={paperId} /></Panel></div>}
      </div>
      <PillBar
        label="Workspace panels"
        hideFrom="lg"
        items={MOBILE_TABS.filter((t) => shown(t.id)).map(({ id, label, Icon }) => ({
          key: id,
          label,
          icon: <Icon aria-hidden className="size-5" />,
          active: phone === id,
          onSelect: () => { setMobile(id); },
        }))}
      />
      </>
      )}
    </div>
    </CitationProvider>
  );
}
