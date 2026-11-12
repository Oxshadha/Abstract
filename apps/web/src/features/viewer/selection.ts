import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

import type { ExplainLevel } from "./citation-context";

const LEVEL_KEY = "abstract.explain-level";

export interface TextSelection {
  page: number;
  text: string;
  rect: { top: number; bottom: number; left: number; width: number };
}

/** The chosen Explain level, remembered on this device (spec 015 AC4). */
export function useExplainLevel(): [ExplainLevel, (level: ExplainLevel) => void] {
  const [level, setLevel] = useState<ExplainLevel>(() => {
    try {
      return window.localStorage.getItem(LEVEL_KEY) === "expert" ? "expert" : "plain";
    } catch {
      return "plain";
    }
  });
  const choose = useCallback((next: ExplainLevel) => {
    setLevel(next);
    try {
      window.localStorage.setItem(LEVEL_KEY, next);
    } catch {
      // private mode: the choice lasts for this visit only
    }
  }, []);
  return [level, choose];
}

/**
 * While dragging, keep pdf.js's `endOfContent` box right after the selection's end, as pdf.js's
 * own viewer does. Otherwise moving past the end of a line (between lines, into a margin) hits
 * that box at the end of the page, and Safari selects the rest of the page.
 */
function keepEndNearFocus(selection: Selection): void {
  if (selection.rangeCount === 0) return;
  const range = selection.getRangeAt(0);
  const node = range.endContainer;
  const anchor = node instanceof Element ? node : node.parentElement;
  if (!anchor || anchor.classList.contains("endOfContent")) return;
  const layer = anchor.closest(".textLayer");
  const end = layer?.querySelector(".endOfContent");
  if (!layer || !(end instanceof HTMLElement) || anchor === layer || !anchor.parentElement) return;
  end.style.width = `${String(layer.clientWidth)}px`;
  end.style.height = `${String(layer.clientHeight)}px`;
  anchor.parentElement.insertBefore(end, anchor.nextSibling);
}

/** Put every moved `endOfContent` back at the end of its text layer. */
function resetEnds(root: HTMLElement): void {
  for (const end of root.querySelectorAll<HTMLElement>(".endOfContent")) {
    const layer = end.closest(".textLayer");
    if (!layer || end.parentElement === layer && end === layer.lastElementChild) continue;
    end.style.width = "";
    end.style.height = "";
    layer.append(end);
  }
}

/** Text selected inside `root`'s pages, read when a pointer is released or the keyboard moves. */
function readSelection(root: HTMLElement): TextSelection | null {
  const selection = document.getSelection();
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return null;
  const range = selection.getRangeAt(0);
  if (!root.contains(range.startContainer)) return null; // started outside the paper
  const start = range.startContainer;
  const element = start instanceof Element ? start : start.parentElement;
  // A selection across two pages uses the first page (spec 015 edge cases).
  const pageEl = element?.closest("[data-page]");
  const page = Number(pageEl?.getAttribute("data-page"));
  if (!pageEl || !Number.isFinite(page) || page < 1) return null;
  let scope: Range = range;
  if (!pageEl.contains(range.endContainer)) {
    const layer = pageEl.querySelector(".textLayer");
    if (!layer) return null;
    scope = range.cloneRange();
    scope.setEnd(layer, layer.childNodes.length);
  }
  const text = scope.toString().replace(/\s+/g, " ").trim();
  if (!text) return null;
  const box = typeof range.getBoundingClientRect === "function" ? range.getBoundingClientRect() : null;
  return { page, text, rect: { top: box?.top ?? 0, bottom: box?.bottom ?? 0, left: box?.left ?? 0, width: box?.width ?? 0 } };
}

/**
 * The text selected in the paper (spec 015 AC3): mouse and touch selections are read when the
 * pointer is released, keyboard selections as they change. Escape, scrolling the pages or a
 * click elsewhere closes it.
 */
export function useTextSelection(root: RefObject<HTMLElement | null>, toolbar: RefObject<HTMLElement | null>) {
  const [selected, setSelected] = useState<TextSelection | null>(null);
  const pointerDown = useRef(false);
  const close = useCallback(() => { setSelected(null); }, []);

  useEffect(() => {
    const read = () => {
      const el = root.current;
      setSelected(el ? readSelection(el) : null);
    };
    const onDown = (event: PointerEvent) => {
      if (toolbar.current?.contains(event.target as Node)) return;
      pointerDown.current = true;
      setSelected(null);
    };
    const onUp = () => {
      if (!pointerDown.current) return;
      pointerDown.current = false;
      setTimeout(() => {
        read(); // after the browser settles the selection
        if (root.current) resetEnds(root.current);
      }, 0);
    };
    const onChange = () => {
      if (pointerDown.current) {
        // A drag in progress: keep it from jumping to the end of the page; read on release.
        const selection = document.getSelection();
        if (selection && root.current?.contains(selection.anchorNode)) keepEndNearFocus(selection);
        return;
      }
      read();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelected(null);
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("pointerup", onUp);
    document.addEventListener("selectionchange", onChange);
    document.addEventListener("keydown", onKey);
    const el = root.current;
    el?.addEventListener("scroll", close, { passive: true });
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("pointerup", onUp);
      document.removeEventListener("selectionchange", onChange);
      document.removeEventListener("keydown", onKey);
      el?.removeEventListener("scroll", close);
    };
  }, [root, toolbar, close]);

  return { selected, close };
}

