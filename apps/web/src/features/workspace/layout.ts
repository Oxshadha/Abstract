import { useEffect, useState } from "react";

/**
 * Workspace layout (D79, owner): Paper and Summary side by side by default, each can be hidden;
 * the divider is draggable; chat opens only when asked for. Remembered per device.
 */
export interface Layout {
  paper: boolean;
  summary: boolean;
  chat: boolean;
  split: number; // Paper's share of the width, in percent
}

export const DEFAULT_LAYOUT: Layout = { paper: true, summary: true, chat: false, split: 50 };
export const MIN_SPLIT = 25;
export const MAX_SPLIT = 75;
const KEY = "abstract.workspace.layout";

export function clampSplit(value: number): number {
  return Math.min(MAX_SPLIT, Math.max(MIN_SPLIT, Math.round(value)));
}

function load(): Layout {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return DEFAULT_LAYOUT;
    const value = JSON.parse(raw) as Partial<Layout>;
    const layout: Layout = {
      paper: value.paper !== false,
      summary: value.summary !== false,
      chat: value.chat === true,
      split: clampSplit(typeof value.split === "number" ? value.split : 50),
    };
    return layout.paper || layout.summary ? layout : DEFAULT_LAYOUT;
  } catch {
    return DEFAULT_LAYOUT; // storage blocked or corrupted: defaults
  }
}

export function useWorkspaceLayout() {
  const [layout, setLayout] = useState<Layout>(load);
  useEffect(() => {
    try {
      window.localStorage.setItem(KEY, JSON.stringify(layout));
    } catch {
      // private mode: the layout simply is not remembered
    }
  }, [layout]);

  const toggle = (panel: "paper" | "summary") => {
    setLayout((current) => {
      const other = panel === "paper" ? "summary" : "paper";
      if (current[panel] && !current[other]) return current; // keep one main panel visible
      return { ...current, [panel]: !current[panel] };
    });
  };
  return {
    layout,
    toggle,
    setChat: (chat: boolean) => {
      setLayout((current) => ({ ...current, chat }));
    },
    setSplit: (split: number) => {
      setLayout((current) => ({ ...current, split: clampSplit(split) }));
    },
  };
}

const DESKTOP = "(min-width: 1024px)";

/** Render only the layout for this screen size (no hidden duplicate panels or streams). */
export function useIsDesktop(): boolean {
  const query = () =>
    typeof window.matchMedia === "function" ? window.matchMedia(DESKTOP).matches : true;
  const [desktop, setDesktop] = useState(query);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(DESKTOP);
    const onChange = () => {
      setDesktop(list.matches);
    };
    list.addEventListener("change", onChange);
    return () => {
      list.removeEventListener("change", onChange);
    };
  }, []);
  return desktop;
}
