import { Lightbulb, MessageSquareQuote } from "lucide-react";
import { useEffect, useState, type RefObject } from "react";
import { createPortal } from "react-dom";

import type { ExplainLevel } from "./citation-context";
import type { TextSelection } from "./selection";

const MARGIN = 8;

/** Explain (with its level) and Ask, floating next to the selected text. */
export function SelectionToolbar({
  selection,
  toolbarRef,
  level,
  onLevel,
  onExplain,
  onAsk,
}: {
  selection: TextSelection;
  toolbarRef: RefObject<HTMLDivElement | null>;
  level: ExplainLevel;
  onLevel: (level: ExplainLevel) => void;
  onExplain: () => void;
  onAsk: () => void;
}) {
  const [measured, setWidth] = useState<number | null>(null); // hidden until measured
  useEffect(() => {
    setWidth(toolbarRef.current?.offsetWidth ?? 0);
  }, [toolbarRef]);
  const width = measured ?? 0;
  const { rect } = selection;
  const height = 48;
  const above = rect.top - height - MARGIN;
  const top = above >= MARGIN ? above : rect.bottom + MARGIN;
  const center = rect.left + rect.width / 2;
  const left = Math.max(MARGIN, Math.min(center - width / 2, window.innerWidth - width - MARGIN));
  const button = "inline-flex min-h-11 items-center gap-1.5 rounded-md px-2.5 text-sm font-medium hover:bg-muted";
  const levelButton = (value: ExplainLevel, label: string) => (
    <button
      type="button"
      role="radio"
      aria-checked={level === value}
      onClick={() => { onLevel(value); }}
      className={`min-h-9 rounded-sm px-2 text-xs ${level === value ? "bg-primary text-primary-text" : "text-text-secondary hover:bg-muted"}`}
    >
      {label}
    </button>
  );

  return createPortal(
    <div
      ref={toolbarRef}
      role="toolbar"
      aria-label="Selected text"
      // Keep the selection when a button is pressed.
      onPointerDown={(e) => { e.preventDefault(); }}
      onMouseDown={(e) => { e.preventDefault(); }}
      style={{ position: "fixed", top, left, visibility: measured === null ? "hidden" : "visible" }}
      className="z-50 flex items-center gap-0.5 rounded-lg border border-border bg-surface p-1 shadow-overlay"
    >
      <button type="button" onClick={onExplain} className={button}>
        <Lightbulb aria-hidden className="size-4" />
        Explain
      </button>
      <span role="radiogroup" aria-label="Explain level" className="flex items-center gap-0.5 rounded-md border border-border p-0.5">
        {levelButton("plain", "Plain")}
        {levelButton("expert", "Expert")}
      </span>
      <span aria-hidden className="mx-0.5 h-6 w-px bg-border" />
      <button type="button" onClick={onAsk} className={button}>
        <MessageSquareQuote aria-hidden className="size-4" />
        Ask
      </button>
    </div>,
    document.body,
  );
}
