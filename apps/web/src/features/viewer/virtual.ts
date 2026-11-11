const BUFFER = 2; // AC6: render the viewport plus 2 pages either side

/** First and last page index to render for a scroll position (spec 008 AC6). */
export function visibleWindow(offsets: number[], heights: number[], top: number, viewport: number): [number, number] {
  let first = 0;
  while (first < offsets.length - 1 && (offsets[first] ?? 0) + (heights[first] ?? 0) < top) first += 1;
  let last = first;
  while (last < offsets.length - 1 && (offsets[last + 1] ?? 0) < top + viewport) last += 1;
  return [Math.max(0, first - BUFFER), Math.min(offsets.length - 1, last + BUFFER)];
}
