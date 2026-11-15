/**
 * Paper-aware correction of dictated research terms (spec 020 AC7), in the browser, no model call.
 * The vocabulary comes from the paper itself (title, headings, summary): acronyms and mixed-case
 * terms such as BLEU, WMT, LoRA, GPT-4. A dictated word that is one edit away from such a term
 * ("blue" for BLEU), the same letters in another case ("lora"), or the term spelled out letter by
 * letter ("w m t") is replaced; each change is reported so the reader can see and undo it.
 */

export interface Correction {
  from: string;
  to: string;
}

const TERM = /\b(?=[A-Za-z0-9-]*[A-Z][A-Za-z0-9-]*[A-Z0-9])[A-Za-z][A-Za-z0-9-]{1,11}\b/g;
const COMMON = new Set(["The", "This", "We", "It", "In", "On", "For", "And", "Our", "To", "Of", "A", "An", "AI"]);

/** Distinctive terms of the paper: acronyms and mixed case words (at least two capitals). */
export function buildVocabulary(texts: string[]): string[] {
  const seen = new Set<string>();
  for (const text of texts) {
    for (const match of text.matchAll(TERM)) {
      const word = match[0];
      if (!COMMON.has(word) && (word.match(/[A-Z]/g) ?? []).length >= 2) seen.add(word);
    }
  }
  return [...seen];
}

/** Edit distance with adjacent swaps (Damerau), so "blue" is one step from "bleu". */
function distance(a: string, b: string): number {
  const d: number[][] = Array.from({ length: a.length + 1 }, (_, i) => Array.from({ length: b.length + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0)));
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      const row = d[i] as number[];
      const up = d[i - 1] as number[];
      row[j] = Math.min((up[j] ?? 0) + 1, (row[j - 1] ?? 0) + 1, (up[j - 1] ?? 0) + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) row[j] = Math.min(row[j] ?? 0, ((d[i - 2] as number[])[j - 2] ?? 0) + 1);
    }
  }
  return (d[a.length] as number[])[b.length] ?? 0;
}

function bare(term: string): string {
  return term.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function match(word: string, vocabulary: string[]): string | undefined {
  const w = bare(word);
  if (w.length < 2) return undefined;
  const exact = vocabulary.find((t) => bare(t) === w);
  if (exact) return exact === word ? undefined : exact;
  if (w.length < 4) return undefined; // short words are too easy to confuse
  return vocabulary.find((t) => {
    const b = bare(t);
    return b.length >= 4 && b[0] === w[0] && distance(w, b) === 1;
  });
}

/** Correct dictated text against the paper's vocabulary; returns the text and what changed. */
export function correctTerms(text: string, vocabulary: string[]): { text: string; changes: Correction[] } {
  if (vocabulary.length === 0) return { text, changes: [] };
  const changes: Correction[] = [];
  // Letters spelled one by one: "w m t" -> "WMT".
  let out = text.replace(/\b(?:[a-zA-Z] ){1,5}[a-zA-Z]\b/g, (spelled) => {
    const joined = spelled.replace(/ /g, "");
    const term = vocabulary.find((t) => bare(t) === joined.toLowerCase());
    if (!term) return spelled;
    changes.push({ from: spelled, to: term });
    return term;
  });
  out = out.replace(/[A-Za-z][A-Za-z0-9-]*/g, (word) => {
    const term = match(word, vocabulary);
    if (!term) return word;
    changes.push({ from: word, to: term });
    return term;
  });
  return { text: out, changes };
}
