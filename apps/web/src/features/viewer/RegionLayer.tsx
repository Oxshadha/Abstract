import { MessageSquare, X } from "lucide-react";
import { useRef, type KeyboardEvent, type PointerEvent } from "react";

import type { PageBox } from "./citation-context";

const MIN = 0.02; // the server's minimum region size each way (AC11)
const STEP = 0.01;

type Drag = { mode: "draw" | "move" | "resize"; startX: number; startY: number; origin: PageBox } | null;

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

function normalised(a: { x: number; y: number }, b: { x: number; y: number }): PageBox {
  return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: Math.abs(a.x - b.x), height: Math.abs(a.y - b.y) };
}

function bounded(box: PageBox): PageBox {
  const width = clamp(box.width, MIN, 1);
  const height = clamp(box.height, MIN, 1);
  return { x: clamp(box.x, 0, 1 - width), y: clamp(box.y, 0, 1 - height), width, height };
}

/**
 * Draw, move and resize a box on one page (spec 009 AC10): mouse and touch by dragging, keyboard
 * with the arrow keys (Shift resizes). Coordinates are page fractions, the only thing sent to
 * the server; the crop itself is rendered there (AC11).
 */
export function RegionLayer({
  page,
  box,
  onChange,
  onAsk,
  onCancel,
}: {
  page: number;
  box: PageBox | null;
  onChange: (box: PageBox | null) => void;
  onAsk: () => void;
  onCancel: () => void;
}) {
  const layer = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag>(null);

  const point = (event: PointerEvent) => {
    const rect = layer.current?.getBoundingClientRect();
    if (!rect || rect.width === 0 || rect.height === 0) return { x: 0, y: 0 };
    return { x: clamp((event.clientX - rect.left) / rect.width, 0, 1), y: clamp((event.clientY - rect.top) / rect.height, 0, 1) };
  };

  const begin = (mode: "draw" | "move" | "resize", event: PointerEvent) => {
    event.stopPropagation();
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const p = point(event);
    drag.current = { mode, startX: p.x, startY: p.y, origin: box ?? { x: p.x, y: p.y, width: 0, height: 0 } };
    if (mode === "draw") onChange({ x: p.x, y: p.y, width: 0, height: 0 });
  };

  const move = (event: PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const p = point(event);
    const dx = p.x - d.startX;
    const dy = p.y - d.startY;
    if (d.mode === "draw") onChange(normalised({ x: d.startX, y: d.startY }, p));
    if (d.mode === "move") onChange(bounded({ ...d.origin, x: d.origin.x + dx, y: d.origin.y + dy }));
    if (d.mode === "resize") onChange(bounded({ ...d.origin, width: d.origin.width + dx, height: d.origin.height + dy }));
  };

  const end = () => {
    const d = drag.current;
    drag.current = null;
    if (d?.mode === "draw" && box && (box.width < MIN || box.height < MIN)) onChange(null); // a click, not a box
  };

  const keys = (event: KeyboardEvent) => {
    if (!box) return;
    const moves: Record<string, [number, number]> = { ArrowLeft: [-STEP, 0], ArrowRight: [STEP, 0], ArrowUp: [0, -STEP], ArrowDown: [0, STEP] };
    const delta = moves[event.key];
    if (delta) {
      event.preventDefault();
      const [dx, dy] = delta;
      onChange(bounded(event.shiftKey ? { ...box, width: box.width + dx, height: box.height + dy } : { ...box, x: box.x + dx, y: box.y + dy }));
    } else if (event.key === "Enter") {
      event.preventDefault();
      onAsk();
    } else if (event.key === "Escape") {
      event.preventDefault();
      onCancel();
    }
  };

  const ready = box !== null && box.width >= MIN && box.height >= MIN;
  const below = box ? box.y + box.height < 0.85 : true;

  return (
    <div
      ref={layer}
      onPointerDown={(e) => { begin("draw", e); }}
      onPointerMove={move}
      onPointerUp={end}
      onPointerCancel={end}
      className="absolute inset-0 z-10 cursor-crosshair touch-none select-none"
      aria-label={`Draw a region on page ${String(page)}`}
    >
      {box && (
        <div
          role="group"
          tabIndex={0}
          aria-label={`Selected region on page ${String(page)}. Arrow keys move it, Shift with arrow keys resizes it, Enter asks about it.`}
          onPointerDown={(e) => { begin("move", e); }}
          onKeyDown={keys}
          className="absolute cursor-move rounded-sm outline-2 outline-text outline-dashed focus-visible:outline-solid"
          style={{
            left: `${String(box.x * 100)}%`,
            top: `${String(box.y * 100)}%`,
            width: `${String(box.width * 100)}%`,
            height: `${String(box.height * 100)}%`,
            backgroundColor: "color-mix(in srgb, var(--color-highlight) 22%, transparent)",
          }}
        >
          <span
            aria-hidden
            onPointerDown={(e) => { begin("resize", e); }}
            className="absolute -right-2 -bottom-2 size-5 cursor-nwse-resize rounded-sm border-2 border-text bg-surface"
          />
          {ready && (
            <div
              onPointerDown={(e) => { e.stopPropagation(); }}
              className={`absolute left-0 flex gap-1 whitespace-nowrap ${below ? "top-full mt-3" : "bottom-full mb-3"}`}
            >
              <button
                type="button"
                onClick={onAsk}
                className="inline-flex min-h-11 items-center gap-2 rounded-pill bg-primary px-4 text-sm font-medium text-primary-text shadow-overlay"
              >
                <MessageSquare aria-hidden className="size-4" />
                Ask about this region
              </button>
              <button
                type="button"
                aria-label="Cancel region"
                onClick={onCancel}
                className="inline-flex size-11 items-center justify-center rounded-pill border border-border bg-surface shadow-overlay"
              >
                <X aria-hidden className="size-4" />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
