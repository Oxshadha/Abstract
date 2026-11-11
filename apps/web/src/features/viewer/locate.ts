/**
 * Find a quoted sentence in a page's text-layer items (spec 008 AC4, D81).
 * Text is normalised (case, whitespace, line-end hyphenation); an exact match is tried first,
 * then the best fuzzy window of words.
 */
export interface TextPiece {
  str: string;
  hasEOL?: boolean;
}

export interface Position {
  item: number;
  offset: number;
}

export interface Located {
  start: Position;
  end: Position; // exclusive offset in end.item
  exact: boolean;
}

interface Mapped {
  text: string;
  positions: Position[]; // one per character of `text`
}

function build(items: TextPiece[]): Mapped {
  let text = "";
  const positions: Position[] = [];
  const push = (ch: string, pos: Position) => {
    const space = /\s/.test(ch);
    if (space && (text.length === 0 || text.endsWith(" "))) return;
    text += space ? " " : ch.toLowerCase();
    positions.push(pos);
  };
  items.forEach((piece, item) => {
    const str = piece.str;
    const hyphenated = Boolean(piece.hasEOL) && /\w-$/.test(str);
    const last = hyphenated ? str.length - 1 : str.length; // "architec-" + "ture"
    for (let offset = 0; offset < last; offset += 1) {
      const ch = str[offset] ?? "";
      if (ch !== "­") push(ch, { item, offset });
    }
    if (piece.hasEOL && !hyphenated) push(" ", { item, offset: str.length });
  });
  return { text, positions };
}

function normalise(quote: string): string {
  return quote.replace(/­/g, "").replace(/(\w)-\s+(\w)/g, "$1$2").replace(/\s+/g, " ").trim().toLowerCase();
}

function range(mapped: Mapped, from: number, to: number, exact: boolean): Located | null {
  const start = mapped.positions[from];
  const last = mapped.positions[to - 1];
  if (!start || !last) return null;
  return { start, end: { item: last.item, offset: last.offset + 1 }, exact };
}

const WORD = /[\p{L}\p{N}]+/gu;

export function locate(items: TextPiece[], quote: string, minScore = 0.7): Located | null {
  const needle = normalise(quote);
  if (needle.length < 8) return null;
  const mapped = build(items);
  const at = mapped.text.indexOf(needle);
  if (at >= 0) return range(mapped, at, at + needle.length, true);

  // Fuzzy: the window of page words that shares the most words with the quote.
  const words = [...mapped.text.matchAll(WORD)].map((m) => ({ word: m[0], start: m.index, end: m.index + m[0].length }));
  const wanted = needle.match(WORD) ?? [];
  if (wanted.length === 0 || words.length === 0) return null;
  const size = wanted.length;
  const target = new Map<string, number>();
  for (const w of wanted) target.set(w, (target.get(w) ?? 0) + 1);
  let best = { score: 0, from: 0 };
  for (let from = 0; from + Math.min(size, words.length) <= words.length; from += 1) {
    const counts = new Map(target);
    let hits = 0;
    for (const w of words.slice(from, from + size)) {
      const left = counts.get(w.word) ?? 0;
      if (left > 0) {
        hits += 1;
        counts.set(w.word, left - 1);
      }
    }
    const score = hits / size;
    if (score > best.score) best = { score, from };
  }
  if (best.score < minScore) return null;
  const first = words[best.from];
  const lastWord = words[Math.min(best.from + size, words.length) - 1];
  if (!first || !lastWord) return null;
  return range(mapped, first.start, lastWord.end, false);
}

const ESCAPE: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (ch) => ESCAPE[ch] ?? ch);
}

/** HTML for one text item with the located part wrapped in <mark> (text is always escaped). */
export function markItem(str: string, item: number, located: Located | null): string {
  if (!located || item < located.start.item || item > located.end.item) return escapeHtml(str);
  const from = item === located.start.item ? located.start.offset : 0;
  const to = item === located.end.item ? located.end.offset : str.length;
  return (
    escapeHtml(str.slice(0, from)) +
    `<mark class="citation-highlight" data-citation="true">${escapeHtml(str.slice(from, to))}</mark>` +
    escapeHtml(str.slice(to))
  );
}
