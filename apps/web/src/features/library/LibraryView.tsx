import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { ArrowDownUp, FileUp, LayoutGrid, List, Plus, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState, type RefObject } from "react";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ListRowSkeleton, Loading } from "@/components/feedback/Skeleton";
import { Select } from "@/components/menu/Select";
import { FieldError } from "@/components/status/FieldError";
import { useFlag } from "@/features/flags/api";
import { useUploadFlow } from "@/features/papers/useUploadFlow";
import { useMediaQuery } from "@/features/workspace/layout";

import { libraryKeys, listCollections, listLibrary, type LibraryParams, type Sort } from "./api";
import { PaperCard, PaperRow } from "./PaperItems";
import { CollectionChips } from "./SidebarCollections";
import { withDefaults, type LibrarySearch } from "./search-params";
import { TrashView } from "./TrashView";

type Filter = "all" | "starred" | "trash";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "starred", label: "Starred" },
  { key: "trash", label: "Recently deleted" },
];

function activeFilter(params: LibraryParams): Filter {
  return params.trash ? "trash" : params.starred ? "starred" : "all";
}

const SORTS: { value: Sort; label: string }[] = [
  { value: "added", label: "Recently added" },
  { value: "opened", label: "Recently opened" },
  { value: "title", label: "Title A to Z" },
];

type View = "list" | "grid";
const VIEW_KEY = "abstract.library.view";

function readView(): View {
  try {
    return localStorage.getItem(VIEW_KEY) === "grid" ? "grid" : "list";
  } catch {
    return "list";
  }
}

/** "Add Paper" (AC1): the compact upload once the Library has papers; drops work anywhere. */
function AddPaper({ dropTarget }: { dropTarget: RefObject<HTMLDivElement | null> }) {
  const flow = useUploadFlow();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    const el = dropTarget.current;
    if (!el) return;
    const over = (event: globalThis.DragEvent) => {
      if (!event.dataTransfer?.types.includes("Files")) return;
      event.preventDefault();
      setDragging(true);
    };
    const leave = (event: globalThis.DragEvent) => {
      if (event.target === el) setDragging(false);
    };
    const drop = (event: globalThis.DragEvent) => {
      if (!event.dataTransfer?.files.length) return;
      event.preventDefault();
      setDragging(false);
      flow.dropped(event.dataTransfer.files);
    };
    el.addEventListener("dragover", over);
    el.addEventListener("dragleave", leave);
    el.addEventListener("drop", drop);
    return () => {
      el.removeEventListener("dragover", over);
      el.removeEventListener("dragleave", leave);
      el.removeEventListener("drop", drop);
    };
  }, [dropTarget, flow]);

  return (
    <div className="flex flex-col items-end gap-2">
      {flow.busy ? (
        <div className="flex w-64 max-w-full items-center gap-2" aria-live="polite">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm" title={flow.fileName}>{flow.fileName}</p>
            <div role="progressbar" aria-label="Upload progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={flow.percent} className="mt-1 h-1.5 overflow-hidden rounded-pill bg-muted">
              <div className="h-full rounded-pill bg-primary transition-[width] motion-reduce:transition-none" style={{ width: `${String(flow.percent)}%` }} />
            </div>
          </div>
          <button type="button" aria-label="Cancel upload" onClick={flow.cancel} className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted">
            <X aria-hidden className="size-4" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          disabled={!flow.online}
          onClick={() => input.current?.click()}
          className="inline-flex min-h-11 items-center gap-2 rounded-pill bg-primary px-5 font-medium text-primary-text disabled:opacity-50"
        >
          <Plus aria-hidden className="size-5" />
          Add Paper
        </button>
      )}
      <input
        ref={input}
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(event) => {
          flow.start(event.target.files?.[0]);
          event.target.value = "";
        }}
      />
      <FieldError id="add-paper-error" message={flow.error} />
      {dragging && (
        <div aria-hidden className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center bg-text/40">
          <div className="flex flex-col items-center gap-2 rounded-xl border-2 border-dashed border-primary-text bg-surface px-10 py-8">
            <FileUp className="size-10" />
            <p className="font-medium">Drop the PDF to upload it</p>
          </div>
        </div>
      )}
    </div>
  );
}

function Toolbar({ params, view, onView }: { params: LibraryParams; view: View; onView: (v: View) => void }) {
  const navigate = useNavigate({ from: "/app/library" });
  const bin = useFlag("recently_deleted");
  const set = (change: LibrarySearch) => {
    void navigate({ search: (prev: LibrarySearch) => ({ ...prev, ...change }) });
  };
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div role="group" aria-label="Filter papers" className="flex max-w-full overflow-x-auto rounded-pill border border-border p-1">
        {FILTERS.filter((f) => f.key !== "trash" || bin).map((f) => {
          const active = activeFilter(params) === f.key;
          return (
            <button
              key={f.key}
              type="button"
              aria-pressed={active}
              aria-label={f.key === "trash" ? f.label : undefined}
              onClick={() => { set({ starred: f.key === "starred" ? true : undefined, trash: f.key === "trash" ? true : undefined }); }}
              className={`inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-pill px-3 text-sm ${active ? "bg-primary text-primary-text" : "text-text-secondary hover:text-text"}`}
            >
              {f.key === "trash" ? (
                <>
                  <Trash2 aria-hidden className="size-4" />
                  {/* Phones: the icon alone keeps the filters on one line (icons over words). */}
                  <span aria-hidden className="hidden sm:inline">{f.label}</span>
                </>
              ) : (
                f.label
              )}
            </button>
          );
        })}
      </div>
      {params.trash ? null : (
      <span className="ml-auto flex items-center gap-2">
        <Select
          label="Sort"
          value={params.sort}
          icon={<ArrowDownUp aria-hidden className="size-4 shrink-0" />}
          options={SORTS}
          onChange={(sort) => { set({ sort: sort === "added" ? undefined : sort }); }}
          width="w-48"
        />
        <span role="group" aria-label="View" className="hidden rounded-md border border-border sm:flex">
          <button type="button" aria-label="Grid view" aria-pressed={view === "grid"} onClick={() => { onView("grid"); }} className={`inline-flex size-11 items-center justify-center rounded-md ${view === "grid" ? "bg-muted" : "hover:bg-muted"}`}>
            <LayoutGrid aria-hidden className="size-4" />
          </button>
          <button type="button" aria-label="List view" aria-pressed={view === "list"} onClick={() => { onView("list"); }} className={`inline-flex size-11 items-center justify-center rounded-md ${view === "list" ? "bg-muted" : "hover:bg-muted"}`}>
            <List aria-hidden className="size-4" />
          </button>
        </span>
      </span>
      )}
    </div>
  );
}

/** Library home (spec 013, D82): upload, every paper with filters, sort and infinite loading. */
export function LibraryView() {
  const search = useSearch({ from: "/app/library" });
  const params = withDefaults(search);
  const page = useRef<HTMLDivElement>(null);
  const sentinel = useRef<HTMLDivElement>(null);
  const [chosenView, setView] = useState<View>(readView);
  // Phones always get the compact list: a one-column "grid" is just bigger rows (owner review).
  const wide = useMediaQuery("(min-width: 640px)");
  const view: View = wide ? chosenView : "list";
  const collections = useQuery({ queryKey: libraryKeys.collections, queryFn: listCollections, enabled: Boolean(params.collection) });
  const collection = collections.data?.find((c) => c.id === params.collection);

  const papers = useInfiniteQuery({
    queryKey: libraryKeys.list(params),
    queryFn: ({ pageParam, signal }) => listLibrary(params, pageParam, signal),
    enabled: !params.trash,
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    staleTime: 30_000, // cached between visits; uploads, stars and edits refresh it (AC10)
    refetchInterval: (q) => (q.state.data?.pages.some((p) => p.items.some((i) => i.status === "processing")) ? 5000 : false),
  });
  const items = papers.data?.pages.flatMap((p) => p.items) ?? [];
  const empty = papers.isSuccess && items.length === 0;

  // AC2, AC11: load the next page when the end of the list scrolls into view.
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = papers;
  useEffect(() => {
    const el = sentinel.current;
    if (!el || !hasNextPage || typeof IntersectionObserver !== "function") return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting) && !isFetchingNextPage) void fetchNextPage();
    }, { rootMargin: "600px" });
    observer.observe(el);
    return () => { observer.disconnect(); };
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const changeView = (next: View) => {
    setView(next);
    try {
      localStorage.setItem(VIEW_KEY, next);
    } catch {
      // private mode: the choice lasts for this visit
    }
  };

  return (
    // Header and toolbar stay put; only the list scrolls (design principle 5).
    <div ref={page} className="flex h-full min-h-0 flex-col gap-4 px-4 pt-4 sm:pt-6 md:px-8">
      <header className="flex flex-wrap items-start gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-3xl font-bold tracking-tight">{params.trash ? "Recently deleted" : (collection?.name ?? "Your Library")}</h1>
          <p className="mt-1 hidden text-text-secondary sm:block">
            {collection ? `${String(collection.paper_count)} ${collection.paper_count === 1 ? "paper" : "papers"} in this collection.` : "Upload, organize, summarize, and explore your research papers."}
          </p>
        </div>
        <AddPaper dropTarget={page} />
      </header>

      {(
        <section aria-labelledby="papers-heading" className="flex min-h-0 flex-1 flex-col gap-4">
          <h2 id="papers-heading" className="sr-only">Papers</h2>
          <CollectionChips />
          <Toolbar params={params} view={view} onView={changeView} />
          <div className="-mx-4 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain px-4 pt-1 pb-28 md:-mx-8 md:px-8 md:pb-10">
          {params.trash ? (
            <TrashView />
          ) : papers.isPending ? (
            <Loading label="Loading your papers">
              <ListRowSkeleton />
              <ListRowSkeleton />
              <ListRowSkeleton />
            </Loading>
          ) : papers.isError ? (
            <div role="alert" className="rounded-lg border border-border bg-surface p-4">
              <p>{papers.error.message}</p>
              <button type="button" onClick={() => void papers.refetch()} className="mt-2 min-h-11 underline">Try again</button>
            </div>
          ) : empty ? (
            <EmptyState
              icon={FileUp}
              title={params.collection ? "This collection is empty" : params.starred ? "No starred papers" : "No papers yet"}
              description={
                params.collection
                  ? "Add papers with the menu on any paper in your Library."
                  : params.starred
                    ? "Star a paper to find it here quickly."
                    : "Add a paper to get a structured summary and ask questions about it."
              }
            />
          ) : (
            <ul
              aria-label="Papers"
              className={view === "grid" ? "grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3" : "flex flex-col gap-3"}
            >
              {items.map((paper) => (view === "grid" ? <PaperCard key={paper.id} paper={paper} /> : <PaperRow key={paper.id} paper={paper} />))}
            </ul>
          )}
          <div ref={sentinel} aria-hidden />
          {!params.trash && hasNextPage && (
            <button
              type="button"
              disabled={isFetchingNextPage}
              onClick={() => void fetchNextPage()}
              className="mx-auto min-h-11 rounded-pill border border-border px-5 hover:bg-muted disabled:opacity-50"
            >
              {isFetchingNextPage ? "Loading" : "Show more"}
            </button>
          )}
          </div>
        </section>
      )}
    </div>
  );
}

