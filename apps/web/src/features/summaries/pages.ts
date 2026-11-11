/** "p. 2-6" for consecutive pages, "p. 1, 4" otherwise (no en dashes in UI text, D62). */
export function pageLabel(pages: number[]): string {
  const unique = [...new Set(pages)].sort((a, b) => a - b);
  if (unique.length === 0) return "";
  const first = unique[0] ?? 0;
  const last = unique[unique.length - 1] ?? 0;
  if (unique.length > 1 && last - first === unique.length - 1) return `p. ${String(first)}-${String(last)}`;
  return `p. ${unique.join(", ")}`;
}
