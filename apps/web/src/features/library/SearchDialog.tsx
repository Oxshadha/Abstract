import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { FileText, Loader2, Search, TextQuote, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import { useOnline } from "@/components/feedback/useOnline";

import { libraryKeys, listCollections, searchPapers, type SearchResults } from "./api";
import { highlight, MIN_QUERY, useDebounced } from "./search-text";

type Hit =
  | { kind: "paper"; id: string; title: string; detail: string }
  | { kind: "passage"; id: string; title: string; page: number; snippet: string };

function hits(results: SearchResults | undefined): Hit[] {
  if (!results) return [];
  return [
    ...results.papers.map<Hit>((p) => ({
      kind: "paper",
      id: p.id,
      title: p.title,
      detail: [p.authors.slice(0, 2).join(", ") + (p.authors.length > 2 ? " et al." : ""), p.year ? String(p.year) : ""].filter(Boolean).join(" · "),
    })),
    ...results.passages.map<Hit>((p) => ({ kind: "passage", id: p.paper_id, title: p.paper_title, page: p.page, snippet: p.snippet })),
  ];
}

/** Search across the user's papers (spec 013 AC8). Opened by the top bar or Ctrl/Cmd+K. */
export function SearchDialog({ open, onClose, collection }: { open: boolean; onClose: () => void; collection: string | null }) {
  const ref = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const navigate = useNavigate();
  const online = useOnline();
  const [text, setText] = useState("");
  const [active, setActive] = useState(0);
  const [scoped, setScoped] = useState(true);
  const query = useDebounced(text.trim());
  const scope = scoped ? collection : null;
  const collections = useQuery({ queryKey: libraryKeys.collections, queryFn: listCollections, enabled: Boolean(collection) && open });
  const scopeName = collections.data?.find((c) => c.id === collection)?.name;

  const results = useQuery({
    queryKey: libraryKeys.search(query, scope),
    queryFn: ({ signal }) => searchPapers(query, scope, signal), // a newer query aborts this one
    enabled: open && query.length >= MIN_QUERY,
    staleTime: 60_000, // typing back to an earlier query costs no request
    placeholderData: (previous) => previous,
  });
  const list = query.length >= MIN_QUERY ? hits(results.data) : [];

  useEffect(() => {
    const el = ref.current as (Partial<HTMLDialogElement> & HTMLElement) | null;
    if (!el) return;
    if (open && !el.hasAttribute("open")) {
      if (typeof el.showModal === "function") el.showModal();
      else el.setAttribute("open", "");
      setText("");
      setActive(0);
      setScoped(true);
      requestAnimationFrame(() => input.current?.focus());
    } else if (!open && el.hasAttribute("open")) {
      if (typeof el.close === "function") el.close();
      else el.removeAttribute("open");
    }
  }, [open]);

  const choose = (hit: Hit) => {
    onClose();
    if (hit.kind === "paper") {
      void navigate({ to: "/app/papers/$paperId", params: { paperId: hit.id } });
    } else {
      // Open at the page with the passage highlighted, the same path citations use (008).
      const quote = hit.snippet.replace(/[«»]/g, "").replace(/\s*…\s*/g, " ").trim();
      void navigate({ to: "/app/papers/$paperId", params: { paperId: hit.id }, search: { page: hit.page, quote } });
    }
  };

  const onKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") { event.preventDefault(); setActive((a) => Math.min(list.length - 1, a + 1)); }
    if (event.key === "ArrowUp") { event.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    if (event.key === "Enter") {
      const hit = list[active];
      if (hit) { event.preventDefault(); choose(hit); }
    }
  };

  const papers = list.filter((h) => h.kind === "paper");
  const passages = list.filter((h) => h.kind === "passage");
  const renderHit = (hit: Hit, index: number) => (
    <li
      key={`${hit.kind}-${hit.id}-${hit.kind === "passage" ? String(hit.page) + hit.snippet.slice(0, 20) : ""}`}
      id={`${listId}-${String(index)}`}
      role="option"
      aria-selected={index === active}
      onMouseEnter={() => { setActive(index); }}
      onClick={() => { choose(hit); }}
      className={`flex min-h-11 cursor-pointer items-start gap-3 rounded-md px-3 py-2 ${index === active ? "bg-muted" : ""}`}
    >
      {hit.kind === "paper" ? <FileText aria-hidden className="mt-0.5 size-4 shrink-0" /> : <TextQuote aria-hidden className="mt-0.5 size-4 shrink-0" />}
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium">{hit.title}</span>
        {hit.kind === "paper" ? (
          hit.detail && <span className="block truncate text-sm text-text-secondary">{hit.detail}</span>
        ) : (
          <span className="block text-sm text-text-secondary">
            <span className="font-medium text-text">{`p. ${String(hit.page)}: `}</span>
            {highlight(hit.snippet)}
          </span>
        )}
      </span>
    </li>
  );

  return (
    <dialog
      ref={ref}
      aria-label="Search papers"
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onClick={(event) => { if (event.target === ref.current) onClose(); }}
      className="m-0 h-full max-h-none w-full max-w-none bg-surface p-0 text-text backdrop:bg-text/40 sm:mx-auto sm:mt-[10vh] sm:h-auto sm:max-h-[75vh] sm:max-w-2xl sm:rounded-xl sm:border sm:border-border sm:shadow-overlay"
    >
      {open && (
        <div className="flex h-full max-h-[inherit] flex-col">
          <div className="flex items-center gap-2 border-b border-border px-3">
            <Search aria-hidden className="size-5 shrink-0 text-text-secondary" />
            <input
              ref={input}
              type="search"
              role="combobox"
              aria-expanded={list.length > 0}
              aria-controls={listId}
              aria-activedescendant={list.length ? `${listId}-${String(active)}` : undefined}
              aria-label="Search papers"
              placeholder="Search papers, authors, or text"
              value={text}
              maxLength={200}
              onChange={(e) => { setText(e.target.value); setActive(0); }}
              onKeyDown={onKey}
              className="min-h-14 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-text-secondary"
            />
            {results.isFetching && <Loader2 aria-hidden className="size-4 animate-spin text-text-secondary motion-reduce:animate-none" />}
            <button type="button" aria-label="Close search" onClick={onClose} className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted">
              <X aria-hidden className="size-5" />
            </button>
          </div>
          {collection && scopeName && (
            <div className="flex items-center gap-2 border-b border-border px-4 py-2 text-sm">
              <span className="text-text-secondary">{scoped ? `In ${scopeName}` : "In all papers"}</span>
              <button type="button" onClick={() => { setScoped(!scoped); }} className="ml-auto min-h-9 rounded-md px-2 underline">
                {scoped ? "Search all papers" : `Search ${scopeName} only`}
              </button>
            </div>
          )}
          <div className="min-h-0 flex-1 overflow-auto p-2">
            <p className="sr-only" aria-live="polite">
              {query.length >= MIN_QUERY && results.isSuccess ? `${String(list.length)} results` : ""}
            </p>
            {!online ? (
              <p className="p-4 text-sm text-text-secondary">You are offline. Search works again when you reconnect.</p>
            ) : text.trim().length < MIN_QUERY ? (
              <p className="p-4 text-sm text-text-secondary">Type at least 2 characters to search titles, authors and the text of your papers.</p>
            ) : results.isError ? (
              <p role="alert" className="p-4 text-sm">{results.error.message}</p>
            ) : results.isSuccess && list.length === 0 && !results.isFetching ? (
              <p className="p-4 text-sm text-text-secondary">No results for "{query}".</p>
            ) : (
              <ul id={listId} role="listbox" aria-label="Search results" className="flex flex-col gap-0.5">
                {papers.length > 0 && <li role="presentation" className="px-3 pt-2 pb-1 text-xs font-medium tracking-wide text-text-secondary uppercase">Papers</li>}
                {papers.map((hit) => renderHit(hit, list.indexOf(hit)))}
                {passages.length > 0 && <li role="presentation" className="px-3 pt-3 pb-1 text-xs font-medium tracking-wide text-text-secondary uppercase">In papers</li>}
                {passages.map((hit) => renderHit(hit, list.indexOf(hit)))}
              </ul>
            )}
          </div>
        </div>
      )}
    </dialog>
  );
}
