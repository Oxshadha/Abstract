import { useLayoutEffect, type CSSProperties, type RefObject } from "react";

const GAP = 4;
const MARGIN = 8; // keep popups this far from the window edge

/** Render a floating popup with this style first; `useFloating` then places it. */
export const FLOATING_STYLE: CSSProperties = { position: "fixed", top: 0, left: 0, visibility: "hidden" };

/**
 * Position a popup (menu, dropdown) next to its trigger in viewport coordinates, so it can be
 * rendered in a portal and never be clipped by a scrolling sidebar or panel. Flips above the
 * trigger when there is no room below; dismisses on resize or on scroll outside the popup.
 */
export function useFloating(
  open: boolean,
  trigger: RefObject<HTMLElement | null>,
  popup: RefObject<HTMLElement | null>,
  align: "left" | "right",
  onDismiss: () => void,
): void {
  useLayoutEffect(() => {
    const anchor = trigger.current?.getBoundingClientRect();
    const el = popup.current;
    if (!open || !anchor || !el) return;
    const width = el.offsetWidth;
    const height = el.offsetHeight;
    let left = align === "right" ? anchor.right - width : anchor.left;
    left = Math.max(MARGIN, Math.min(left, window.innerWidth - width - MARGIN));
    const below = anchor.bottom + GAP;
    const fitsBelow = below + height <= window.innerHeight - MARGIN;
    const top = fitsBelow || anchor.top - GAP - height < MARGIN ? below : anchor.top - GAP - height;
    Object.assign(el.style, {
      top: `${String(top)}px`,
      left: `${String(left)}px`,
      maxHeight: `${String(window.innerHeight - 2 * MARGIN)}px`,
      visibility: "visible",
    });
    const onScroll = (event: Event) => {
      if (!el.contains(event.target as Node)) onDismiss();
    };
    window.addEventListener("resize", onDismiss);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      window.removeEventListener("resize", onDismiss);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open, trigger, popup, align, onDismiss]);
}
