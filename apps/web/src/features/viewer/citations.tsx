import { useMemo, useState, type ReactNode } from "react";

import { CitationContext, MAX_QUOTE_CHARS, type AskQuote, type AskRegion, type CitationApi, type CitationTarget } from "./citation-context";

export function CitationProvider({
  children,
  onOpen,
  onAskRegion,
}: {
  children: ReactNode;
  onOpen?: () => void;
  onAskRegion?: () => void; // show the chat (desktop panel, phone tab)
}) {
  const [target, setTarget] = useState<CitationTarget | null>(null);
  const [region, setRegion] = useState<AskRegion | null>(null);
  const [quote, setQuote] = useState<AskQuote | null>(null);
  const value = useMemo<CitationApi>(
    () => ({
      target,
      open: (page, quote) => {
        onOpen?.(); // show the Paper panel (D79) or switch to the Paper tab on phones
        setTarget({ page, quote, id: Date.now() + Math.random() });
      },
      openBox: (page, box, label) => {
        onOpen?.();
        setTarget({ page, quote: "", box, label, id: Date.now() + Math.random() });
      },
      clear: () => {
        setTarget(null);
      },
      region,
      askRegion: (next) => {
        setQuote(null); // one attachment at a time
        setRegion(next);
        onAskRegion?.();
      },
      clearRegion: () => {
        setRegion(null);
      },
      quote,
      askQuote: (next) => {
        const text = next.text.replace(/\s+/g, " ").trim();
        if (!text) return;
        setRegion(null); // one attachment at a time
        setQuote({ ...next, text: text.slice(0, MAX_QUOTE_CHARS), trimmed: text.length > MAX_QUOTE_CHARS, id: Date.now() + Math.random() });
        onAskRegion?.();
      },
      clearQuote: () => {
        setQuote(null);
      },
    }),
    [target, onOpen, region, quote, onAskRegion],
  );
  return <CitationContext.Provider value={value}>{children}</CitationContext.Provider>;
}
