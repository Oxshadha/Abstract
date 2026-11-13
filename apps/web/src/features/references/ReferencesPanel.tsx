import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileDown, Quote } from "lucide-react";
import type { ReactNode } from "react";

import { ListRowSkeleton } from "@/components/feedback/Skeleton";

import { getReferences, referenceKeys, type ReferenceItem } from "./api";

const POLL_MS = 4000;

function authors(names: string[]): string {
  if (names.length === 0) return "";
  if (names.length <= 2) return names.join(" and ");
  return `${names[0] ?? ""} et al.`;
}

function meta(item: ReferenceItem): string {
  const m = item.match;
  if (!m) return "";
  const cited = m.citations == null ? "" : `${m.citations.toLocaleString()} citation${m.citations === 1 ? "" : "s"}`;
  return [authors(m.authors), m.year ? String(m.year) : "", m.venue ?? "", cited].filter(Boolean).join(" · ");
}

function IconLink({ href, label, children }: { href: string; label: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={label}
      title={label}
      className="inline-flex size-11 shrink-0 items-center justify-center rounded-md text-text-secondary hover:bg-muted hover:text-text"
    >
      {children}
    </a>
  );
}

/** One reference: the matched paper with its links, or the entry's own text when unmatched (AC6). */
function Row({ item }: { item: ReferenceItem }) {
  const label = item.label ?? String(item.n);
  const m = item.match;
  return (
    <li className="flex min-w-0 items-start gap-3 rounded-lg border border-border bg-surface p-3">
      <span aria-hidden className="mt-0.5 w-7 shrink-0 text-right text-sm tabular-nums text-text-secondary">{label}</span>
      <div className="min-w-0 flex-1">
        {m ? (
          <>
            <p className="line-clamp-2 font-medium" title={m.title}>
              <span className="sr-only">Reference {label}: </span>
              {m.title}
            </p>
            <p className="truncate text-sm text-text-secondary">{meta(item)}</p>
          </>
        ) : (
          <p className="line-clamp-3 font-reading text-sm text-text-secondary" title={item.raw}>
            <span className="sr-only">Reference {label}: </span>
            {item.raw}
          </p>
        )}
      </div>
      {m && (
        <div className="-my-1.5 flex shrink-0">
          {m.pdf_url && (
            <IconLink href={m.pdf_url} label={`Open the PDF of ${m.title}`}>
              <FileDown aria-hidden className="size-4" />
            </IconLink>
          )}
          <IconLink href={m.url} label={`Open ${m.title} in Semantic Scholar`}>
            <ExternalLink aria-hidden className="size-4" />
          </IconLink>
        </div>
      )}
    </li>
  );
}

/**
 * What the paper cites (spec 014 AC5, AC6): the paper's own reference list, each entry matched on
 * Semantic Scholar in the background. Entries show at once and fill in as matches arrive.
 */
export function ReferencesPanel({ paperId }: { paperId: string }) {
  const refs = useQuery({
    queryKey: referenceKeys.forPaper(paperId),
    queryFn: () => getReferences(paperId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "matching" ? POLL_MS : false;
    },
  });
  if (refs.isPending) {
    return (
      <div className="flex flex-col gap-2">
        <ListRowSkeleton />
        <ListRowSkeleton />
        <ListRowSkeleton />
      </div>
    );
  }
  if (refs.isError) return <p role="alert" className="text-sm">{refs.error.message}</p>;
  const { status, items } = refs.data;
  if (status === "none" || (status === "pending" && items.length === 0)) {
    return (
      <div className="flex flex-col items-center gap-2 py-12 text-center text-text-secondary">
        <Quote aria-hidden className="size-6" />
        <p className="text-sm">
          {status === "pending" ? "The references appear once the paper is read." : "No reference list was found in this paper."}
        </p>
      </div>
    );
  }
  const matched = items.filter((i) => i.match).length;
  return (
    <div className="flex min-h-0 flex-col gap-3">
      <p aria-live="polite" className="text-sm text-text-secondary">
        {status === "matching"
          ? `${String(items.length)} references. Looking them up on Semantic Scholar.`
          : `${String(items.length)} references, ${String(matched)} found on Semantic Scholar.`}
      </p>
      {/* Desktop uses the width (6b): two columns of rows; phones one clean line per item. */}
      <ol aria-label="References" className="grid gap-2 xl:grid-cols-2">
        {items.map((item) => (
          <Row key={item.n} item={item} />
        ))}
      </ol>
    </div>
  );
}
