import { useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ExternalLink, FileText } from "lucide-react";

import { StatusIcon, StatusPill, type Status } from "@/components/status/StatusPill";
import { getPaper, paperKeys, type Paper } from "@/features/papers/api";
import { formatPages, timeAgo } from "@/features/papers/format";
import { listSummaries, summaryKeys } from "@/features/summaries/api";

import { paperName } from "./format";
import { PaperMenu, StarButton } from "./PaperActions";

const PILL: Record<Paper["status"], { status: Status; label: string }> = {
  processing: { status: "processing", label: "Processing" },
  ready: { status: "success", label: "Ready" },
  failed: { status: "error", label: "Failed" },
};

function byline(paper: Paper): string {
  const authors = paper.authors.length > 2 ? `${paper.authors[0] ?? ""} et al.` : paper.authors.join(", ");
  return [authors, paper.year ? String(paper.year) : "", paper.pages ? formatPages(paper.pages) : ""].filter(Boolean).join(" · ");
}

/** Hovering or focusing a paper loads it and its summaries ahead of the click (AC13). */
function usePrefetch(paper: Paper) {
  const client = useQueryClient();
  return () => {
    if (paper.status !== "ready") return;
    const ignore = () => undefined; // a failed prefetch is retried when the paper opens
    void client.query({ queryKey: paperKeys.detail(paper.id), queryFn: () => getPaper(paper.id), staleTime: 30_000 }).catch(ignore);
    void client.query({ queryKey: summaryKeys.forPaper(paper.id), queryFn: () => listSummaries(paper.id), staleTime: 30_000 }).catch(ignore);
  };
}

function OpenLink({ paper }: { paper: Paper }) {
  const ready = paper.status === "ready";
  const name = paperName(paper);
  return ready ? (
    <Link
      to="/app/papers/$paperId"
      params={{ paperId: paper.id }}
      aria-label={`Open ${name}`}
      className="inline-flex min-h-11 items-center gap-2 rounded-md border border-border px-3 hover:bg-muted"
    >
      <ExternalLink aria-hidden className="size-4" />
      Open
    </Link>
  ) : (
    <Link
      to="/app/papers/$paperId/processing"
      params={{ paperId: paper.id }}
      aria-label={`View ${name} progress`}
      className="inline-flex min-h-11 items-center gap-2 rounded-md border border-border px-3 text-text-secondary hover:bg-muted"
    >
      View
    </Link>
  );
}

/**
 * One paper in a list. Phones get a single clean line: icon, title with status, pages and
 * time beneath, then star and menu as icons; the whole row opens the paper. Wider screens add
 * the status pill, a time column and the Open button.
 */
export function PaperRow({ paper }: { paper: Paper }) {
  const pill = PILL[paper.status];
  const prefetch = usePrefetch(paper);
  const name = paperName(paper);
  const meta = byline(paper);
  return (
    <li
      onMouseEnter={prefetch}
      onFocus={prefetch}
      className="relative flex items-center gap-3 rounded-lg border border-border bg-surface py-2 pr-1 pl-3 sm:gap-4 sm:p-4"
    >
      <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted sm:size-11">
        <FileText aria-hidden className="size-5" />
      </span>
      <div className="min-w-0 flex-1">
        <Link
          to={paper.status === "ready" ? "/app/papers/$paperId" : "/app/papers/$paperId/processing"}
          params={{ paperId: paper.id }}
          className="block truncate font-medium after:absolute after:inset-0 after:rounded-lg hover:underline sm:after:hidden"
          title={name}
        >
          {name}
        </Link>
        <p className="flex min-w-0 items-center gap-1.5 text-sm text-text-secondary">
          <span className="sm:hidden">
            <StatusIcon status={pill.status} label={pill.label} />
          </span>
          <span className="truncate">{meta}</span>
          <span className="shrink-0 sm:hidden">{`${meta ? "· " : ""}${timeAgo(paper.created_at)}`}</span>
        </p>
        {paper.status === "failed" && paper.error_message && <p className="mt-1 text-sm text-text-secondary">{paper.error_message}</p>}
      </div>
      <span className="hidden sm:inline-flex">
        <StatusPill status={pill.status}>{pill.label}</StatusPill>
      </span>
      <span className="hidden w-16 text-right text-sm whitespace-nowrap text-text-secondary sm:inline">{timeAgo(paper.created_at)}</span>
      <span className="hidden sm:inline-flex">
        <OpenLink paper={paper} />
      </span>
      <span className="relative z-10 flex shrink-0 items-center">
        <StarButton paper={paper} />
        <PaperMenu paper={paper} />
      </span>
    </li>
  );
}

export function PaperCard({ paper }: { paper: Paper }) {
  const pill = PILL[paper.status];
  const prefetch = usePrefetch(paper);
  const name = paperName(paper);
  return (
    <li onMouseEnter={prefetch} onFocus={prefetch} className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
      <div className="flex items-start gap-2">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-md bg-muted">
          <FileText aria-hidden className="size-5" />
        </span>
        <span className="ml-auto flex">
          <StarButton paper={paper} />
          <PaperMenu paper={paper} />
        </span>
      </div>
      <Link
        to={paper.status === "ready" ? "/app/papers/$paperId" : "/app/papers/$paperId/processing"}
        params={{ paperId: paper.id }}
        className="line-clamp-2 font-medium hover:underline"
        title={name}
      >
        {name}
      </Link>
      <p className="truncate text-sm text-text-secondary">{byline(paper) || " "}</p>
      <div className="mt-auto flex items-center gap-2">
        <StatusPill status={pill.status}>{pill.label}</StatusPill>
        <span className="ml-auto text-sm text-text-secondary">{timeAgo(paper.created_at)}</span>
      </div>
    </li>
  );
}
