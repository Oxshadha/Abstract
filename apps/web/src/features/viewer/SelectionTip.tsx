import { Lightbulb, SquareDashedMousePointer, X } from "lucide-react";
import { useState } from "react";

const KEY = "abstract.tip.selection";

function seen(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * A one-time tip above the pages (spec 015): how to Explain or Ask about text, and the region
 * tool for tables and figures. Dismissed once per device.
 */
export function SelectionTip({ regions = true }: { regions?: boolean }) {
  const [hidden, setHidden] = useState(seen);
  if (hidden) return null;
  const touch = typeof window.matchMedia === "function" && window.matchMedia("(pointer: coarse)").matches;
  return (
    <div role="note" aria-label="Tip" className="mt-2 flex items-start gap-2 rounded-md border border-border bg-surface p-2 text-sm">
      <Lightbulb aria-hidden className="mt-0.5 size-4 shrink-0" />
      <p className="min-w-0 flex-1">
        {touch ? "Press and hold on text, then drag the handles" : "Select text with the mouse"}
        {" to Explain it or Ask about it."}
        {regions && (
          <>
            {" For a table or figure, use "}
            <SquareDashedMousePointer aria-label="Select region" className="inline size-4 align-text-bottom" />
            {" and draw a box."}
          </>
        )}
      </p>
      <button
        type="button"
        aria-label="Dismiss tip"
        onClick={() => {
          setHidden(true);
          try {
            window.localStorage.setItem(KEY, "1");
          } catch {
            // private mode: shown again next visit
          }
        }}
        className="-m-1 inline-flex size-9 shrink-0 items-center justify-center rounded-md hover:bg-muted"
      >
        <X aria-hidden className="size-4" />
      </button>
    </div>
  );
}
