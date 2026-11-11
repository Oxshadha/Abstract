import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

/** A request to show a cited sentence in the Paper panel (spec 008 AC4). */
export interface CitationTarget {
  page: number;
  quote: string;
  id: number; // new id per click, so clicking the same citation again re-focuses it
}

interface CitationApi {
  target: CitationTarget | null;
  open: (page: number, quote: string) => void;
  clear: () => void;
}

const Context = createContext<CitationApi | null>(null);

export function CitationProvider({ children, onOpen }: { children: ReactNode; onOpen?: () => void }) {
  const [target, setTarget] = useState<CitationTarget | null>(null);
  const value = useMemo<CitationApi>(
    () => ({
      target,
      open: (page, quote) => {
        onOpen?.(); // show the Paper panel (D79) or switch to the Paper tab on phones
        setTarget({ page, quote, id: Date.now() + Math.random() });
      },
      clear: () => {
        setTarget(null);
      },
    }),
    [target, onOpen],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

/** Null outside the Workspace (citations then just expand their quote). */
export function useCitations(): CitationApi | null {
  return useContext(Context);
}
