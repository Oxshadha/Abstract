import { useMemo, useState, type ReactNode } from "react";

import { CitationContext, type CitationApi, type CitationTarget } from "./citation-context";

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
  return <CitationContext.Provider value={value}>{children}</CitationContext.Provider>;
}
