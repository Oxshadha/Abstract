import "react-pdf/dist/Page/TextLayer.css";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { ChevronLeft, ChevronRight, Download, Minus, Plus, RotateCcw } from "lucide-react";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

import { useCitations } from "./citations";
import { getFileUrl, getPageSizes, viewerKeys, type PageSize } from "./api";
import { locate, markItem, type Located, type TextPiece } from "./locate";
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

  const goTo = (page: number) => {
    const el = scroller.current as (Partial<HTMLDivElement> & { scrollTop: number }) | null;
    const top = offsets[page - 1];
    if (!el || top === undefined) return;
    if (el.scrollTo) el.scrollTo({ top, behavior: "auto" });
    else el.scrollTop = top; // browsers without element.scrollTo (tests)
  };

  // AC4: a citation request scrolls to its page; the page highlights it when its text arrives.
  const target = citations?.target ?? null;
  const highlight = target ? { page: target.page, id: target.id, located: found?.id === target.id ? found.located : null } : null;
  useEffect(() => {
    if (target && pages.length > 0) goTo(target.page);
    // goTo depends on layout; scroll only for a new citation
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target?.id, pages.length]);

  // react-pdf reports a page's text once per load, so keep it: a citation for a page that is
  // already on screen is located from this cache.
  const texts = useRef(new Map<number, TextPiece[]>());
  useEffect(() => { texts.current.clear(); }, [paperId]);
  const resolve = () => {
    if (!target || found?.id === target.id) return;
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

  const options = useMemo(() => ({ disableAutoFetch: true, isEvalSupported: false }), []);

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
      <div role="toolbar" aria-label="Paper viewer" className="flex flex-wrap items-center gap-1 border-b border-border pb-2">
        <button type="button" aria-label="Previous page" disabled={current <= 1} onClick={() => { goTo(current - 1); }} className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted disabled:opacity-40">
          <ChevronLeft aria-hidden className="size-5" />
        </button>
        <label className="flex items-center gap-1 text-sm">
          <span className="sr-only">Page</span>
          <input
            key={current}
            type="number"
            min={1}
            max={pages.length || 1}
            defaultValue={current}
            onKeyDown={(e) => {
              if (e.key === "Enter") goTo(Math.min(pages.length, Math.max(1, Number(e.currentTarget.value))));
            }}
            className="h-9 w-12 rounded-md border border-border bg-surface text-center"
          />
          <span className="text-text-secondary">{`/ ${String(pages.length)}`}</span>
        </label>
        <button type="button" aria-label="Next page" disabled={current >= pages.length} onClick={() => { goTo(current + 1); }} className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted disabled:opacity-40">
          <ChevronRight aria-hidden className="size-5" />
        </button>
        <span className="ml-auto flex items-center gap-1">
          <button type="button" aria-label="Zoom out" onClick={() => { setZoom(ZOOMS.filter((z) => z < scale - 0.01).at(-1) ?? ZOOMS[0] ?? 0.5); }} className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted">
            <Minus aria-hidden className="size-4" />
          </button>
          <select
            aria-label="Zoom"
            value={zoom === "fit" ? "fit" : String(zoom)}
            onChange={(e) => { setZoom(e.target.value === "fit" ? "fit" : Number(e.target.value)); }}
            className="h-9 rounded-md border border-border bg-surface px-2 text-sm"
          >
            <option value="fit">Fit width</option>
            {ZOOMS.map((z) => (
              <option key={z} value={String(z)}>{`${String(Math.round(z * 100))}%`}</option>
            ))}
          </select>
          <button type="button" aria-label="Zoom in" onClick={() => { setZoom(ZOOMS.find((z) => z > scale + 0.01) ?? ZOOMS.at(-1) ?? 2); }} className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted">
            <Plus aria-hidden className="size-4" />
          </button>
        </span>
      </div>
      <p className="sr-only" aria-live="polite">{announcement}</p>
      {highlight && found?.id === highlight.id && !highlight.located && (
        <p className="mt-2 text-sm text-text-secondary">{announcement}</p>
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
        onClick={() => { if (highlight?.located) { citations?.clear(); } }}
        className="relative mt-2 min-h-0 flex-1 overflow-auto rounded-md bg-muted"
      >
        {/* react-pdf suspends by default; a suspend reaching the app's outer boundary would hide
            the whole Workspace and reset its effects, cancelling a streaming chat answer. */}
        <Suspense fallback={null}>
        {file.data && pages.length > 0 && (
          <Document
            suspense={false}
            key={attempt}
            file={file.data}
            options={options}
            onLoadError={() => { setFailed("The PDF could not be loaded."); }}
            loading=""
          >
            <div style={{ height: total, position: "relative" }}>
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
                      customTextRenderer={({ str, itemIndex }) => markItem(str, itemIndex, highlight?.page === p.page ? highlight.located : null)}
                    />
                  )}
                </div>
              ))}
            </div>
          </Document>
        )}
        </Suspense>
      </div>
    </div>
  );
}
