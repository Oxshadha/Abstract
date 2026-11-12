import "react-pdf/dist/Page/TextLayer.css";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import workerUrl from "pdfjs-dist/legacy/build/pdf.worker.min.mjs?url"; // legacy: see vite.config.ts
import { ChevronLeft, ChevronRight, Download, Minus, Plus, RotateCcw, SquareDashedMousePointer } from "lucide-react";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

import { Select } from "@/components/menu/Select";

import { useCitations, type PageBox } from "./citation-context";
import { PDF_ASSETS } from "./pdf-assets";
import { getFileUrl, getPageSizes, viewerKeys, type PageSize } from "./api";
import { locate, markItem, type Located, type TextPiece } from "./locate";
import { RegionLayer } from "./RegionLayer";
import { useExplainLevel, useTextSelection } from "./selection";
import { SelectionTip } from "./SelectionTip";
import { SelectionToolbar } from "./SelectionToolbar";
import { visibleWindow } from "./virtual";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl; // AC7: pdf.js parses in its worker

const GAP = 12;
const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2];

type Zoom = "fit" | number;

/** Paper panel viewer (spec 008): virtualised pages, toolbar, sentence highlight for citations. */
export function PdfViewer({ paperId }: { paperId: string }) {
  const queryClient = useQueryClient();
  const citations = useCitations();
  const file = useQuery({ queryKey: viewerKeys.fileUrl(paperId), queryFn: () => getFileUrl(paperId), staleTime: 4 * 60_000 });
  const sizes = useQuery({ queryKey: viewerKeys.pages(paperId), queryFn: () => getPageSizes(paperId), staleTime: Infinity });
  const scroller = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [scroll, setScroll] = useState({ top: 0, height: 800 });
  const [zoom, setZoom] = useState<Zoom>("fit");
  const [failed, setFailed] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [found, setFound] = useState<{ id: number; located: Located | null } | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const frame = useRef<number | null>(null);
  // Ask about this region (spec 009 AC10): drawing mode and the box being drawn.
  const [selecting, setSelecting] = useState(false);
  const [selection, setSelection] = useState<{ page: number; box: PageBox } | null>(null);
  // Explain or Ask about selected text (spec 015 AC3 to AC5).
  const toolbar = useRef<HTMLDivElement>(null);
  const text = useTextSelection(scroller, toolbar);
  const [level, setLevel] = useExplainLevel();
  const sendQuote = (mode: "ask" | "explain") => {
    if (!text.selected) return;
    citations?.askQuote({ page: text.selected.page, text: text.selected.text, mode, level });
    document.getSelection()?.removeAllRanges();
    text.close();
  };

  // AC8: one layout update per animation frame for scroll and resize.
  const measure = useCallback(() => {
    if (frame.current !== null) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = null;
      const el = scroller.current;
      if (!el) return;
      setWidth(el.clientWidth);
      setScroll({ top: el.scrollTop, height: el.clientHeight });
    });
  }, []);
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    measure();
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(measure) : null;
    observer?.observe(el);
    return () => {
      observer?.disconnect();
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      frame.current = null; // otherwise measure() would think a frame is pending and never run again
    };
  }, [measure, sizes.data]);

  const pages: PageSize[] = useMemo(() => sizes.data ?? [], [sizes.data]);
  const widest = Math.max(1, ...pages.map((p) => p.width));
  const scale = zoom === "fit" ? Math.max(0.3, (width - 24) / widest) : zoom;
  const heights = pages.map((p) => p.height * scale);
  const offsets = heights.reduce<number[]>((acc, _h, i) => [...acc, i === 0 ? 0 : (acc[i - 1] ?? 0) + (heights[i - 1] ?? 0) + GAP], []);
  const total = (offsets.at(-1) ?? 0) + (heights.at(-1) ?? 0);
  const [first, last] = pages.length ? visibleWindow(offsets, heights, scroll.top, scroll.height) : [0, -1];
  const current = Math.min(pages.length, Math.max(1, offsets.findIndex((o, i) => o + (heights[i] ?? 0) > scroll.top + scroll.height / 3) + 1));

  const goTo = (page: number, within = 0) => {
    const el = scroller.current as (Partial<HTMLDivElement> & { scrollTop: number }) | null;
    const pageTop = offsets[page - 1];
    // `within` (0 to 1) scrolls to a spot inside the page, e.g. a table's top edge.
    const top = pageTop === undefined ? undefined : Math.max(0, pageTop + within * (heights[page - 1] ?? 0) - 24);
    if (!el || top === undefined) return;
    if (el.scrollTo) el.scrollTo({ top, behavior: "auto" });
    else el.scrollTop = top; // browsers without element.scrollTo (tests)
  };

  // AC4: a citation request scrolls to its page; the page highlights it when its text arrives.
  const target = citations?.target ?? null;
  const highlight = target ? { page: target.page, id: target.id, located: found?.id === target.id ? found.located : null } : null;
  // Scroll for a new target, and again while the layout settles right after it (the viewer may
  // have been hidden behind Figures & tables and is only now measured): never later, so a reader
  // who scrolled away is not pulled back when they resize a panel.
  const targetAt = useRef(0);
  useEffect(() => {
    targetAt.current = Date.now();
  }, [target?.id]);
  // Keep the reader's place when the panel width (and so the page scale) changes, e.g. when
  // the chat opens or the divider moves: re-anchor to the same spot of the same page.
  const anchor = useRef<{ page: number; within: number; scale: number } | null>(null);
  useEffect(() => {
    const index = Math.max(0, current - 1);
    const height = heights[index] ?? 0;
    if (height > 0 && anchor.current?.scale === scale) {
      anchor.current = { page: current, within: Math.min(1, Math.max(0, (scroll.top - (offsets[index] ?? 0)) / height)), scale };
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scroll.top]);
  useEffect(() => {
    const previous = anchor.current;
    anchor.current = previous ? { ...previous, scale } : { page: current, within: 0, scale };
    if (!previous || previous.scale === scale || pages.length === 0) return;
    if (target && Date.now() - targetAt.current <= 1500) return; // a citation is settling
    goTo(previous.page, previous.within + 24 / Math.max(1, heights[previous.page - 1] ?? 1));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scale]);
  useEffect(() => {
    if (!target || pages.length === 0 || Date.now() - targetAt.current > 1500) return;
    goTo(target.page, target.box?.y ?? 0);
    // goTo depends on layout; scroll for a new citation and while its layout settles
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target?.id, pages.length, scale]);

  // react-pdf reports a page's text once per load, so keep it: a citation for a page that is
  // already on screen is located from this cache.
  const texts = useRef(new Map<number, TextPiece[]>());
  useEffect(() => { texts.current.clear(); }, [paperId]);
  const resolve = () => {
    if (!target || found?.id === target.id) return;
    if (target.box) return; // a table, figure or region: outlined from its box, no text to find
    const items = texts.current.get(target.page);
    if (!items) return; // located when the page's text arrives
    const located = locate(items, target.quote);
    setFound({ id: target.id, located });
    setAnnouncement(
      located ? `Showing the cited sentence on page ${String(target.page)}.` : `Sentence not found on this page; showing page ${String(target.page)}.`,
    );
    requestAnimationFrame(() => {
      const mark = scroller.current?.querySelector('mark[data-citation="true"]') as Partial<HTMLElement> | null;
      mark?.scrollIntoView?.({ block: "center" });
    });
  };
  useEffect(resolve); // cheap: returns at once unless a new target has its text ready
  const onText = (pageNumber: number, items: TextPiece[]) => {
    texts.current.set(pageNumber, items);
    resolve();
  };

  // One text renderer per page, kept while that page's highlight is unchanged: react-pdf rebuilds
  // a text layer whenever its renderer changes, which would drop the reader's text selection on
  // every re-render (spec 015 AC3).
  const highlightPage = highlight?.page ?? null;
  const highlightLocated = highlight?.located ?? null;
  const renderers = useMemo(() => {
    const cache = new Map<number, (item: { str: string; itemIndex: number }) => string>();
    return (page: number) => {
      let renderer = cache.get(page);
      if (!renderer) {
        const located = highlightPage === page ? highlightLocated : null;
        renderer = ({ str, itemIndex }) => markItem(str, itemIndex, located);
        cache.set(page, renderer);
      }
      return renderer;
    };
  }, [highlightPage, highlightLocated]);

  const options = useMemo(() => ({ disableAutoFetch: true, isEvalSupported: false, ...PDF_ASSETS }), []);

  if (failed || file.isError || sizes.isError) {
    return (
      <div role="alert" className="flex flex-col items-start gap-3 p-2">
        <p>{failed ?? "The PDF could not be shown."}</p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => {
              setFailed(null);
              setAttempt(attempt + 1);
              void queryClient.invalidateQueries({ queryKey: viewerKeys.fileUrl(paperId) });
              void sizes.refetch();
            }}
            className="inline-flex min-h-11 items-center gap-2 rounded-md border border-border px-3 hover:bg-muted"
          >
            <RotateCcw aria-hidden className="size-4" />
            Try again
          </button>
          {file.data && (
            <a href={file.data} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-2 rounded-md border border-border px-3 hover:bg-muted">
              <Download aria-hidden className="size-4" />
              Download PDF
            </a>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-96 flex-col">
      {/* One line at any panel width (container queries): zoom steps hide when the panel is
          narrow, the zoom menu stays. */}
      <div role="toolbar" aria-label="Paper viewer" className="@container flex flex-nowrap items-center gap-0.5 border-b border-border pb-2">
        <button type="button" aria-label="Previous page" disabled={current <= 1} onClick={() => { goTo(current - 1); }} className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted disabled:opacity-40">
          <ChevronLeft aria-hidden className="size-5" />
        </button>
        <label className="flex items-center gap-1 text-sm">
          <span className="sr-only">Page</span>
          <input
            key={current}
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            defaultValue={current}
            onFocus={(e) => { e.currentTarget.select(); }}
            onKeyDown={(e) => {
              const n = Number.parseInt(e.currentTarget.value, 10);
              if (e.key === "Enter" && Number.isFinite(n)) goTo(Math.min(pages.length, Math.max(1, n)));
            }}
            className="h-9 w-11 rounded-md border border-border bg-surface text-center tabular-nums"
          />
          <span className="text-text-secondary">{`/ ${String(pages.length)}`}</span>
        </label>
        <button type="button" aria-label="Next page" disabled={current >= pages.length} onClick={() => { goTo(current + 1); }} className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted disabled:opacity-40">
          <ChevronRight aria-hidden className="size-5" />
        </button>
        <button
          type="button"
          aria-pressed={selecting}
          aria-label="Select region"
          title="Select a region to ask about"
          onClick={() => { setSelecting(!selecting); setSelection(null); }}
          className={`inline-flex size-11 items-center justify-center rounded-md ${selecting ? "bg-primary text-primary-text" : "hover:bg-muted"}`}
        >
          <SquareDashedMousePointer aria-hidden className="size-5" />
        </button>
        <span className="ml-auto flex shrink-0 items-center gap-0.5">
          <button type="button" aria-label="Zoom out" onClick={() => { setZoom(ZOOMS.filter((z) => z < scale - 0.01).at(-1) ?? ZOOMS[0] ?? 0.5); }} className="hidden size-11 items-center justify-center rounded-md hover:bg-muted @md:inline-flex">
            <Minus aria-hidden className="size-4" />
          </button>
          <Select
            label="Zoom"
            value={zoom === "fit" ? "fit" : String(zoom)}
            options={[{ value: "fit", label: "Fit width" }, ...ZOOMS.map((z) => ({ value: String(z), label: `${String(Math.round(z * 100))}%` }))]}
            onChange={(v) => { setZoom(v === "fit" ? "fit" : Number(v)); }}
            width="w-36"
            compact
          />
          <button type="button" aria-label="Zoom in" onClick={() => { setZoom(ZOOMS.find((z) => z > scale + 0.01) ?? ZOOMS.at(-1) ?? 2); }} className="hidden size-11 items-center justify-center rounded-md hover:bg-muted @md:inline-flex">
            <Plus aria-hidden className="size-4" />
          </button>
        </span>
      </div>
      <p className="sr-only" aria-live="polite">
        {target?.box ? `Showing ${target.label ?? "the selection"} on page ${String(target.page)}.` : announcement}
      </p>
      {highlight && !target?.box && found?.id === highlight.id && !highlight.located && (
        <p className="mt-2 text-sm text-text-secondary">{announcement}</p>
      )}
      {citations && <SelectionTip />}
      {text.selected && !selecting && citations && (
        <SelectionToolbar
          selection={text.selected}
          toolbarRef={toolbar}
          level={level}
          onLevel={setLevel}
          onExplain={() => { sendQuote("explain"); }}
          onAsk={() => { sendQuote("ask"); }}
        />
      )}
      <div
        ref={scroller}
        onScroll={measure}
        tabIndex={0}
        role="region"
        aria-label="Paper pages"
        onKeyDown={(e) => {
          if (e.key === "PageDown") { e.preventDefault(); goTo(current + 1); }
          if (e.key === "PageUp") { e.preventDefault(); goTo(current - 1); }
        }}
        // A click off the text clears the cited sentence; a click on text keeps it, since clearing
        // re-renders the text layer and would drop a selection being made (spec 015 AC3).
        onClick={(e) => { if (highlight?.located && !(e.target as Element).closest(".textLayer span")) { citations?.clear(); } }}
        className="relative mt-2 min-h-0 flex-1 overflow-auto rounded-md bg-muted max-lg:pb-24"
      >
        {/* react-pdf suspends by default; a suspend reaching the app's outer boundary would hide
            the whole Workspace and reset its effects, cancelling a streaming chat answer. */}
        <Suspense fallback={null}>
        {/* The full height exists before the PDF loads (react-pdf renders nothing until then),
            so a citation can scroll to its page straight away (008 AC6, 009 AC6). */}
        <div style={{ height: pages.length > 0 ? total : undefined, position: "relative" }}>
        {file.data && pages.length > 0 && (
          <Document
            suspense={false}
            key={attempt}
            file={file.data}
            options={options}
            onLoadError={() => { setFailed("The PDF could not be loaded."); }}
            loading=""
          >
            
              {pages.map((p, i) => (
                <div
                  key={p.page}
                  data-page={p.page}
                  style={{ position: "absolute", top: offsets[i], left: "50%", transform: "translateX(-50%)", width: p.width * scale, height: heights[i] }}
                  className="bg-surface shadow-card"
                >
                  {i >= first && i <= last && (
                    <Page
                      pageNumber={p.page}
                      suspense={false}
                      width={p.width * scale}
                      renderAnnotationLayer={false}
                      renderTextLayer
                      loading=""
                      onRenderError={() => { setFailed("A page could not be shown."); }}
                      onGetTextSuccess={(content) => { onText(p.page, content.items.flatMap((x) => ("str" in x ? [{ str: x.str, hasEOL: x.hasEOL }] : []))); }}
                      customTextRenderer={renderers(p.page)}
                    />
                  )}
                  {selecting && i >= first && i <= last && (
                    <RegionLayer
                      page={p.page}
                      box={selection?.page === p.page ? selection.box : null}
                      onChange={(box) => { setSelection(box ? { page: p.page, box } : null); }}
                      onAsk={() => {
                        if (!selection) return;
                        citations?.askRegion({ page: selection.page, ...selection.box });
                        setSelecting(false);
                        setSelection(null);
                      }}
                      onCancel={() => { setSelection(null); setSelecting(false); }}
                    />
                  )}
                  {target?.box && target.page === p.page && (
                    // Spec 009 AC6: the chosen table, figure or region, in the citation colour.
                    <div
                      aria-hidden
                      data-outline="true"
                      className="pointer-events-none absolute rounded-sm"
                      style={{
                        left: `${String(target.box.x * 100)}%`,
                        top: `${String(target.box.y * 100)}%`,
                        width: `${String(target.box.width * 100)}%`,
                        height: `${String(target.box.height * 100)}%`,
                        outline: "2px solid var(--color-highlight)",
                        backgroundColor: "color-mix(in srgb, var(--color-highlight) 18%, transparent)",
                      }}
                    />
                  )}
                </div>
              ))}
          </Document>
        )}
        </div>
        </Suspense>
      </div>
    </div>
  );
}
