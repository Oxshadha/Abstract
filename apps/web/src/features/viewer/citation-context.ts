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

/** A box drawn on a page to ask about (spec 009 AC10). */
export interface AskRegion extends PageBox {
  page: number;
}

/** Explain level (spec 015 AC4): plain words for a newcomer, or precise for a researcher. */
export type ExplainLevel = "plain" | "expert";
export const MAX_QUOTE_CHARS = 1000; // same as the server

/** Text selected in the PDF to explain or ask about (spec 015 AC4, AC5). */
export interface AskQuote {
  page: number;
  text: string;
  trimmed: boolean; // longer than MAX_QUOTE_CHARS and cut (shown with a note)
  mode: "ask" | "explain";
  level: ExplainLevel;
  id: number;
}

export interface CitationApi {
  target: CitationTarget | null;
  open: (page: number, quote: string) => void;
  /** Show a table, figure or region: scroll to its page and outline its box (spec 009 AC6). */
  openBox: (page: number, box: PageBox, label: string) => void;
  clear: () => void;
  /** The region waiting to be asked about in chat, if any. */
  region: AskRegion | null;
  askRegion: (region: AskRegion) => void;
  clearRegion: () => void;
  /** Selected text waiting in the chat: Explain sends at once, Ask waits for the question. */
  quote: AskQuote | null;
  askQuote: (quote: Omit<AskQuote, "id" | "trimmed">) => void;
  clearQuote: () => void;
}

export const CitationContext = createContext<CitationApi | null>(null);

/** Null outside the Workspace (citations then just expand their quote). */
export function useCitations(): CitationApi | null {
  return useContext(CitationContext);
}
