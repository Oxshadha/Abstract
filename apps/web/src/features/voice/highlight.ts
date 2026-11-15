import { useEffect, type RefObject } from "react";

import type { ReaderState } from "./reader";

const NAME = "voice-sentence";
const ALNUM = /[\p{L}\p{N}]+/gu;
// Between two spoken words the screen may show spaces, punctuation or citation markers like [1, 2].
const GAP = "(?:[^\\p{L}\\p{N}]|\\[\\s*S?\\d+(?:\\s*[,;-]\\s*S?\\d+)*\\s*\\])+";

/** The DOM range showing `sentence` inside `container`, or null when it cannot be matched
 * (for example maths read out in words). Exported for tests. */
export function locateSentence(container: Node, sentence: string): Range | null {
  const words = sentence.match(ALNUM);
  if (!words?.length) return null;
  const nodes: { node: Text; start: number }[] = [];
  let full = "";
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    nodes.push({ node: n as Text, start: full.length });
    full += (n as Text).data;
  }
  const pattern = new RegExp(words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join(GAP), "iu");
  const found = pattern.exec(full);
  if (!found) return null;
  const at = (offset: number) => {
    const hit = [...nodes].reverse().find((n) => n.start <= offset) ?? nodes[0];
    return hit ? { node: hit.node, offset: Math.min(offset - hit.start, hit.node.data.length) } : null;
  };
  const start = at(found.index);
  const end = at(found.index + found[0].length);
  if (!start || !end) return null;
  const range = document.createRange();
  range.setStart(start.node, start.offset);
  range.setEnd(end.node, end.offset);
  return range;
}

function supported(): boolean {
  return typeof CSS !== "undefined" && "highlights" in CSS && typeof Highlight === "function";
}

/** AC2: highlight the sentence being read inside `root` (fields carry data-voice-key) and keep it
 * in view. Off with reduced motion: the field is still marked, the text stays readable. */
export function useSentenceHighlight(root: RefObject<HTMLElement | null>, state: ReaderState, owner: string): void {
  const active = state.owner === owner && state.status !== "idle";
  const segment = state.segments[state.segment];
  const sentence = segment?.sentences[state.sentence];
  const key = segment?.key;
  useEffect(() => {
    if (!active || !supported() || !root.current || !key || !sentence) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const field = root.current.querySelector(`[data-voice-key="${CSS.escape(key)}"]`);
    const range = field ? locateSentence(field, sentence) : null;
    if (!range) return;
    CSS.highlights.set(NAME, new Highlight(range));
    const element = range.startContainer.parentElement;
    element?.scrollIntoView({ block: "nearest" });
    return () => { CSS.highlights.delete(NAME); };
  }, [active, key, sentence, root]);
}
