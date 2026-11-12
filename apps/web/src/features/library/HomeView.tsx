import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";

import { ListRowSkeleton, Loading } from "@/components/feedback/Skeleton";
import { DropZone } from "@/features/papers/DropZone";

import { libraryKeys, listLibrary } from "./api";
import { PaperRow } from "./PaperItems";

export const RECENT_COUNT = 5;

/**
 * Home (D83): upload a research paper, then pick up where you left off. The five papers
 * opened most recently (new uploads count as opened until others are); the Library has the rest.
 */
export function HomeView() {
  const recent = useQuery({
    queryKey: libraryKeys.recent,
    queryFn: ({ signal }) => listLibrary({ sort: "opened" }, null, signal, RECENT_COUNT),
    staleTime: 30_000,
    refetchInterval: (q) => (q.state.data?.items.some((p) => p.status === "processing") ? 5000 : false),
  });
  const items = recent.data?.items ?? [];

  return (
    <div className="flex h-[calc(100dvh-4.4rem)] flex-col gap-4 px-4 pt-4 sm:gap-6 sm:pt-6 md:h-auto md:gap-8 md:px-8 md:pb-10">
      {/* The upload box below already says what to do; a subtitle only repeated it (owner review). */}
      <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Home</h1>
      <DropZone />
      {(recent.isPending || items.length > 0) && (
        // Phones: the upload stays put and only this list scrolls (D86); wider screens scroll the page.
        <section aria-labelledby="recent-heading" className="flex min-h-0 flex-1 flex-col gap-3 md:flex-none md:gap-4">
          <div className="flex items-center gap-2">
            <h2 id="recent-heading" className="font-display text-xl font-bold whitespace-nowrap sm:text-2xl">Recently opened</h2>
            <Link
              to="/app/library"
              title="View all in Library"
              aria-label="View all in Library"
              className="ml-auto inline-flex min-h-11 shrink-0 items-center gap-1 rounded-md px-2 text-sm whitespace-nowrap text-text-secondary hover:text-text sm:text-base"
            >
              View all<span className="hidden sm:inline">{" in Library"}</span>
              <ArrowRight aria-hidden className="size-4" />
            </Link>
          </div>
          {recent.isPending ? (
            <Loading label="Loading your recent papers">
              <ListRowSkeleton />
              <ListRowSkeleton />
            </Loading>
          ) : (
            <ul aria-label="Recently opened papers" className="-mx-1 flex min-h-0 flex-col gap-3 overflow-y-auto overscroll-contain px-1 pb-28 md:overflow-visible md:pb-0">
              {items.map((paper) => <PaperRow key={paper.id} paper={paper} />)}
            </ul>
          )}
        </section>
      )}
      {recent.isError && (
        <p role="alert" className="text-sm text-text-secondary">
          Your recent papers could not be loaded. They are all in your <Link to="/app/library" className="underline">Library</Link>.
        </p>
      )}
    </div>
  );
}
