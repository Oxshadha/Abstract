/**
 * Text preparation for reading aloud (spec 020 AC5c): what a person would say, not what a machine
 * sees. Citation markers, source chips, status labels and Markdown symbols are dropped; short maths
 * is read in words and long maths as "formula"; code, links and table markup are skipped.
 */

const SYMBOLS: Record<string, string> = {
  "=": " equals ",
  "≈": " is about ",
  "≤": " is at most ",
  "≥": " is at least ",
  "<": " is less than ",
  ">": " is greater than ",
  "+": " plus ",
  "×": " times ",
  "*": " times ",
  "/": " over ",
  "^": " to the power of ",
  "√": " square root of ",
  "∑": " sum of ",
  "−": " minus ",
};
const GREEK: Record<string, string> = {
  alpha: "alpha", beta: "beta", gamma: "gamma", delta: "delta", epsilon: "epsilon", theta: "theta",
  lambda: "lambda", mu: "mu", sigma: "sigma", tau: "tau", phi: "phi", pi: "pi", omega: "omega",
};
const LATEX: Record<string, string> = {
  frac: " over ", sqrt: " square root of ", sum: " sum of ", cdot: " times ", times: " times ",
  approx: " is about ", leq: " is at most ", geq: " is at least ", le: " is at most ", ge: " is at least ",
  log: " log ", exp: " exp ", softmax: " softmax ",
};
const MAX_SPOKEN_MATH = 24; // characters of maths read out in words; longer is "formula"

/** A short formula in words ("d_k = d_v" -> "d k equals d v"), a long one as "formula". */
export function speakMath(math: string): string {
  const source = math.trim();
  if (source.length > MAX_SPOKEN_MATH) return " formula ";
  let out = source
    .replace(/\\([a-zA-Z]+)/g, (_, name: string) => GREEK[name] ? ` ${GREEK[name]} ` : (LATEX[name] ?? " "))
    .replace(/[{}]/g, " ")
    .replace(/_/g, " ");
  for (const [symbol, word] of Object.entries(SYMBOLS)) out = out.split(symbol).join(word);
  return ` ${out.replace(/\s+/g, " ").trim()} `;
}

const STATUS_LABELS = /\b(Verified|Inferred|Provisional|Not reported|Edited)\s*[:·]\s*/g;
// [1], [12], [1, 4, 5], [1-3], [S1], [S1, S2], [S1; S3], [p. 4], (p. 4)
const CITATION = /\s*[[(](?:S?\d{1,3}(?:\s*(?:,|;|-|and)\s*S?\d{1,3})*|p{1,2}\.\s*\d+(?:\s*(?:-|to)\s*\d+)?)[\])]/g;
const URL = /\bhttps?:\/\/\S+|\bwww\.\S+/g;

export function prepareForSpeech(markdown: string): string {
  let text = markdown.replace(/\r/g, "");
  text = text.replace(/```[\s\S]*?```/g, " "); // code blocks
  text = text.replace(/`[^`]*`/g, " "); // inline code
  text = text.replace(/^\s*\|.*\|\s*$/gm, " "); // table rows
  text = text.replace(/\$\$([\s\S]+?)\$\$/g, (_, m: string) => speakMath(m));
  text = text.replace(/\$([^$\n]+?)\$/g, (_, m: string) => speakMath(m));
  text = text.replace(/\\\(([\s\S]+?)\\\)/g, (_, m: string) => speakMath(m));
  text = text.replace(/!\[[^\]]*\]\([^)]*\)/g, " "); // images
  text = text.replace(/\[([^\]]+)\]\((?:[^)]*)\)/g, "$1"); // links keep their words
  text = text.replace(URL, " ");
  text = text.replace(CITATION, "");
  text = text.replace(STATUS_LABELS, "");
  text = text.replace(/^\s{0,3}#{1,6}\s+/gm, ""); // headings
  text = text.replace(/^\s*>\s?/gm, ""); // quotes
  text = text.replace(/^\s*(?:[-*+]|\d+[.)])\s+/gm, ""); // list bullets
  text = text.replace(/(\*\*|__|\*|_|~~)(?=\S)([\s\S]*?\S)\1/g, "$2"); // bold, italics, strike
  text = text.replace(/[*_#>|~]+/g, " ");
  // A list item or heading without its own full stop still ends a sentence when spoken.
  text = text.replace(/([^.!?:;\s])\s*\n+/g, "$1.\n");
  return text.replace(/\s+/g, " ").replace(/\s+([.,;:!?])/g, "$1").trim();
}

// Abbreviations whose full stop does not end a sentence.
const ABBREVIATIONS = ["e.g.", "i.e.", "et al.", "etc.", "vs.", "Fig.", "fig.", "Eq.", "eq.", "Sec.", "No.", "Dr.", "Prof.", "approx.", "cf.", "p.", "pp."];
const GUARD = "\u0000";

/** Sentences to speak one by one (AC5: Chrome stops long utterances part way). */
export function splitSentences(text: string): string[] {
  let guarded = text;
  for (const abbr of ABBREVIATIONS) guarded = guarded.split(abbr).join(abbr.replace(/\./g, GUARD));
  guarded = guarded.replace(/(\d)\.(\d)/g, `$1${GUARD}$2`); // 3.5, 28.4
  const parts = guarded.match(/[^.!?]+(?:[.!?]+["')\]]*|$)/g) ?? [];
  return parts.map((s) => s.split(GUARD).join(".").trim()).filter((s) => /[\p{L}\p{N}]/u.test(s));
}
