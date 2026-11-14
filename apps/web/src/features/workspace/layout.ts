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
  chatWidth: number; // the chat panel's width in px (production feedback: chat resizes too)
}

export const DEFAULT_LAYOUT: Layout = { paper: true, summary: true, chat: false, split: 50, chatWidth: 384 };
export const MIN_SPLIT = 25;
export const MAX_SPLIT = 75;
export const MIN_CHAT = 320;
export const MAX_CHAT = 640;
const KEY = "abstract.workspace.layout";

export function clampSplit(value: number): number {
  return Math.min(MAX_SPLIT, Math.max(MIN_SPLIT, Math.round(value)));
}

export function clampChat(value: number): number {
  return Math.min(MAX_CHAT, Math.max(MIN_CHAT, Math.round(value)));
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
      chatWidth: clampChat(typeof value.chatWidth === "number" ? value.chatWidth : DEFAULT_LAYOUT.chatWidth),
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
    showPaper: () => {
      setLayout((current) => ({ ...current, paper: true }));
    },
    setChat: (chat: boolean) => {
      setLayout((current) => ({ ...current, chat }));
    },
    setSplit: (split: number) => {
      setLayout((current) => ({ ...current, split: clampSplit(split) }));
    },
    setChatWidth: (chatWidth: number) => {
      setLayout((current) => ({ ...current, chatWidth: clampChat(chatWidth) }));
    },
  };
}

const DESKTOP = "(min-width: 1024px)";

/** Whether a CSS media query matches, kept in sync as the window changes. */
export function useMediaQuery(media: string): boolean {
  const query = () => (typeof window.matchMedia === "function" ? window.matchMedia(media).matches : true);
  const [matches, setMatches] = useState(query);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(media);
    const onChange = () => {
      setMatches(list.matches);
    };
    list.addEventListener("change", onChange);
    return () => {
      list.removeEventListener("change", onChange);
    };
  }, [media]);
  return matches;
}

/** Render only the layout for this screen size (no hidden duplicate panels or streams). */
export function useIsDesktop(): boolean {
  return useMediaQuery(DESKTOP);
}
