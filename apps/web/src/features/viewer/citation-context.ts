import { createContext, useContext } from "react";

/** A request to show a cited sentence in the Paper panel (spec 008 AC4). */
export interface CitationTarget {
  page: number;
  quote: string;
  id: number; // new id per click, so clicking the same citation again re-focuses it
  box?: PageBox; // a table, figure or region to outline instead of a sentence (spec 009)
  label?: string; // e.g. "Table 2", for the screen-reader announcement
}

/** Page fractions with the origin at the top left, as the API returns them. */
export interface PageBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface CitationApi {
  target: CitationTarget | null;
  open: (page: number, quote: string) => void;
  /** Show a table, figure or region: scroll to its page and outline its box (spec 009 AC6). */
  openBox: (page: number, box: PageBox, label: string) => void;
  clear: () => void;
}

export const CitationContext = createContext<CitationApi | null>(null);

/** Null outside the Workspace (citations then just expand their quote). */
export function useCitations(): CitationApi | null {
  return useContext(CitationContext);
}
