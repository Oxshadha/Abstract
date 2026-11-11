import { Fragment, useEffect, useState, type ReactNode } from "react";

export const MIN_QUERY = 2;
export const DEBOUNCE_MS = 250;

/** The query to send, 250 ms after typing stops; shorter than 2 characters sends nothing (AC10). */
export function useDebounced(value: string, delay = DEBOUNCE_MS): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => { setSettled(value); }, delay);
    return () => { clearTimeout(timer); };
  }, [value, delay]);
  return settled;
}

/** Snippets mark matches with « »; render them as <mark> without any HTML from the server. */
export function highlight(snippet: string): ReactNode {
  return snippet.split(/«|»/).map((part, i) => (i % 2 === 1 ? <mark key={i} className="rounded-sm bg-highlight px-0.5 text-text">{part}</mark> : <Fragment key={i}>{part}</Fragment>));
}
