import { createContext, useContext } from "react";

/** A request to show a cited sentence in the Paper panel (spec 008 AC4). */
export interface CitationTarget {
  page: number;
  quote: string;
  id: number; // new id per click, so clicking the same citation again re-focuses it
}

export interface CitationApi {
  target: CitationTarget | null;
  open: (page: number, quote: string) => void;
  clear: () => void;
}

export const CitationContext = createContext<CitationApi | null>(null);

/** Null outside the Workspace (citations then just expand their quote). */
export function useCitations(): CitationApi | null {
  return useContext(CitationContext);
}
