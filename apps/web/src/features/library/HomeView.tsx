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
    <div className="flex flex-col gap-8 px-4 pt-6 pb-10 md:px-8">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">Home</h1>
        <p className="mt-1 text-text-secondary">Upload a research paper, or pick up where you left off.</p>
      </header>
      <DropZone />
      {(recent.isPending || items.length > 0) && (
        <section aria-labelledby="recent-heading" className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <h2 id="recent-heading" className="font-display text-2xl font-bold">Recently opened</h2>
            <Link to="/app/library" className="ml-auto inline-flex min-h-11 items-center gap-1 rounded-md px-2 text-text-secondary hover:text-text">
              View all in Library
              <ArrowRight aria-hidden className="size-4" />
            </Link>
          </div>
          {recent.isPending ? (
            <Loading label="Loading your recent papers">
              <ListRowSkeleton />
              <ListRowSkeleton />
            </Loading>
          ) : (
            <ul aria-label="Recently opened papers" className="flex flex-col gap-3">
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
