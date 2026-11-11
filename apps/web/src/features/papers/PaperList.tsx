import { useInfiniteQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ExternalLink, FileText, FileUp } from "lucide-react";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ListRowSkeleton, Loading } from "@/components/feedback/Skeleton";
import { StatusPill, type Status } from "@/components/status/StatusPill";

import { listPapers, paperKeys, type Paper } from "./api";
import { DropZone } from "./DropZone";
import { formatBytes, formatPages, timeAgo } from "./format";

const PILL: Record<Paper["status"], { status: Status; label: string }> = {
  processing: { status: "processing", label: "Processing" },
  ready: { status: "success", label: "Ready" },
  failed: { status: "error", label: "Failed" },
};

function PaperRow({ paper }: { paper: Paper }) {
  const pill = PILL[paper.status];
  const meta = [paper.pages ? formatPages(paper.pages) : null, formatBytes(paper.size_bytes)]
    .filter(Boolean)
    .join(" · ");
  const ready = paper.status === "ready";
  return (
    <li className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-surface p-3 sm:flex-nowrap sm:gap-4 sm:p-4">
      <span className="flex size-11 shrink-0 items-center justify-center rounded-md bg-muted">
        <FileText aria-hidden className="size-5" />
      </span>
      <div className="min-w-0 flex-1 basis-[calc(100%-3.5rem)] sm:basis-auto">
        <Link
          to={ready ? "/app/papers/$paperId" : "/app/papers/$paperId/processing"}
          params={{ paperId: paper.id }}
          className="block truncate font-medium hover:underline"
          title={paper.title ?? paper.filename}
        >
          {paper.title ?? paper.filename}
        </Link>
        <p className="truncate text-sm text-text-secondary">{meta}</p>
        {paper.status === "failed" && paper.error_message && (
          <p className="mt-1 text-sm text-text-secondary">{paper.error_message}</p>
        )}
      </div>
      <StatusPill status={pill.status}>{pill.label}</StatusPill>
      <span className="ml-auto text-sm whitespace-nowrap text-text-secondary sm:ml-0 sm:w-16 sm:text-right">
        {timeAgo(paper.created_at)}
      </span>
      {ready ? (
        <Link
          to="/app/papers/$paperId"
          params={{ paperId: paper.id }}
          className="inline-flex min-h-11 items-center gap-2 rounded-md border border-border px-3 hover:bg-muted"
          aria-label={`Open ${paper.title ?? paper.filename}`}
        >
          <ExternalLink aria-hidden className="size-4" />
          Open
        </Link>
      ) : (
        <Link
          to="/app/papers/$paperId/processing"
          params={{ paperId: paper.id }}
          className="inline-flex min-h-11 items-center gap-2 rounded-md border border-border px-3 text-text-secondary hover:bg-muted"
          aria-label={`View progress for ${paper.title ?? paper.filename}`}
        >
          View
        </Link>
      )}
    </li>
  );
}

/** Library list, first slice (spec 004 AC14): newest first, cursor pages, live while processing. */
export function PaperList() {
  const papers = useInfiniteQuery({
    queryKey: paperKeys.list,
    queryFn: ({ pageParam }) => listPapers(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    refetchInterval: (q) =>
      q.state.data?.pages.some((p) => p.items.some((i) => i.status === "processing")) ? 5000 : false,
  });

  if (papers.isPending) {
    return (
      <Loading label="Loading your papers">
        <ListRowSkeleton />
        <ListRowSkeleton />
        <ListRowSkeleton />
      </Loading>
    );
  }
  if (papers.isError) {
    return (
      <div role="alert" className="rounded-lg border border-border bg-surface p-4">
        <p>{papers.error.message}</p>
        <button type="button" onClick={() => void papers.refetch()} className="mt-2 min-h-11 underline">
          Try again
        </button>
      </div>
    );
  }
  const items = papers.data.pages.flatMap((p) => p.items);
  if (items.length === 0) {
    return (
      <EmptyState
        icon={FileUp}
        title="No papers yet"
        description="Upload your first PDF above to get a structured summary and ask questions about it."
      />
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-3" aria-label="Recent papers">
        {items.map((paper) => (
          <PaperRow key={paper.id} paper={paper} />
        ))}
      </ul>
      {papers.hasNextPage && (
        <button
          type="button"
          disabled={papers.isFetchingNextPage}
          onClick={() => void papers.fetchNextPage()}
          className="mx-auto min-h-11 rounded-pill border border-border px-5 hover:bg-muted disabled:opacity-50"
        >
          {papers.isFetchingNextPage ? "Loading" : "Show more"}
        </button>
      )}
    </div>
  );
}

export function LibraryContent() {
  return (
    <div className="flex flex-col gap-8 px-4 pb-10 md:px-8">
      <DropZone />
      <section aria-labelledby="recent-papers" className="flex flex-col gap-4">
        <h2 id="recent-papers" className="font-display text-2xl font-bold">
          Recent papers
        </h2>
        <PaperList />
      </section>
    </div>
  );
}
