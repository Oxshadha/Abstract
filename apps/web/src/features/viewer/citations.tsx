import { useMemo, useState, type ReactNode } from "react";

import { CitationContext, type AskRegion, type CitationApi, type CitationTarget } from "./citation-context";

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
        setRegion(next);
        onAskRegion?.();
      },
      clearRegion: () => {
        setRegion(null);
      },
    }),
    [target, onOpen, region, onAskRegion],
  );
  return <CitationContext.Provider value={value}>{children}</CitationContext.Provider>;
}
