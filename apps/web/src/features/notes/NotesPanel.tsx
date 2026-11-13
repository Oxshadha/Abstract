import { useQuery, useQueryClient } from "@tanstack/react-query";
import { EditorContent, useEditor, useEditorState, type Editor } from "@tiptap/react";
import { Bold, Heading2, Italic, List, ListOrdered, TextQuote } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type MouseEvent, type ReactNode } from "react";

import { SummaryCardSkeleton } from "@/components/feedback/Skeleton";
import { FieldError } from "@/components/status/FieldError";
import { useCitations } from "@/features/viewer/citation-context";

import { MAX_NOTES_CHARS, NotesChangedError, getNotes, notesKeys, saveNotes, type Notes, type NotesDoc } from "./api";
import { notesExtensions } from "./editor";

const SAVE_AFTER_MS = 1000; // AC4: one second after typing stops
const RETRY_AFTER_MS = 5000;
const PLACEHOLDER = "Your notes on this paper. Write here, or save answers from the chat with their sources.";

/** An empty page starts as one empty paragraph (an empty document would have nowhere to type). */
function content(doc: NotesDoc): NotesDoc | null {
  const blocks = (doc as { content?: unknown[] }).content;
  return Array.isArray(blocks) && blocks.length > 0 ? doc : null;
}

type SaveState = "idle" | "saving" | "saved" | "stale" | "too-long" | "error";

const STATE_TEXT: Partial<Record<SaveState, string>> = {
  saving: "Saving",
  saved: "Saved",
  error: "Not saved yet, retrying",
};

function ToolButton({ label, active, onClick, children }: { label: string; active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={active}
      // Keep the selection in the editor while clicking the bar.
      onMouseDown={(event) => { event.preventDefault(); }}
      onClick={onClick}
      className={`inline-flex size-11 shrink-0 items-center justify-center rounded-md ${active ? "bg-muted text-text" : "text-text-secondary hover:bg-muted hover:text-text"}`}
    >
      {children}
    </button>
  );
}

/** Bold, italic, a heading, lists and a quote (D95): the whole formatting bar. */
function Toolbar({ editor }: { editor: Editor }) {
  const active = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      bold: e.isActive("bold"),
      italic: e.isActive("italic"),
      heading: e.isActive("heading"),
      bullets: e.isActive("bulletList"),
      numbers: e.isActive("orderedList"),
      quote: e.isActive("blockquote"),
    }),
  });
  const run = () => editor.chain().focus();
  return (
    <div role="toolbar" aria-label="Formatting" className="flex min-w-0 items-center gap-0.5 overflow-x-auto">
      <ToolButton label="Bold" active={active.bold} onClick={() => run().toggleBold().run()}><Bold aria-hidden className="size-4" /></ToolButton>
      <ToolButton label="Italic" active={active.italic} onClick={() => run().toggleItalic().run()}><Italic aria-hidden className="size-4" /></ToolButton>
      <ToolButton label="Heading" active={active.heading} onClick={() => run().toggleHeading({ level: 2 }).run()}><Heading2 aria-hidden className="size-4" /></ToolButton>
      <ToolButton label="Bulleted list" active={active.bullets} onClick={() => run().toggleBulletList().run()}><List aria-hidden className="size-4" /></ToolButton>
      <ToolButton label="Numbered list" active={active.numbers} onClick={() => run().toggleOrderedList().run()}><ListOrdered aria-hidden className="size-4" /></ToolButton>
      <ToolButton label="Quote" active={active.quote} onClick={() => run().toggleBlockquote().run()}><TextQuote aria-hidden className="size-4" /></ToolButton>
    </div>
  );
}

/**
 * The reader's notes on this paper (spec 014 AC1 to AC4): a simple editor in the reading font that
 * saves itself a second after typing stops. A save carries the version it started from, so a
 * change made in another tab is never overwritten silently; the reader chooses what to keep.
 */
export function NotesPanel({ paperId }: { paperId: string }) {
  const notes = useQuery({ queryKey: notesKeys.forPaper(paperId), queryFn: () => getNotes(paperId) });
  if (notes.isPending) return <SummaryCardSkeleton />;
  if (notes.isError) return <p role="alert" className="text-sm">{notes.error.message}</p>;
  return <NotesEditor paperId={paperId} initial={notes.data} />;
}

function NotesEditor({ paperId, initial }: { paperId: string; initial: Notes }) {
  const queryClient = useQueryClient();
  const citations = useCitations();
  const version = useRef(initial.version);
  const dirty = useRef(false);
  const saving = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [state, setState] = useState<SaveState>("idle");

  const editor = useEditor({
    extensions: notesExtensions(PLACEHOLDER),
    content: content(initial.doc),
    immediatelyRender: true,
    editorProps: {
      attributes: {
        role: "textbox",
        "aria-multiline": "true",
        "aria-label": "Notes",
        class: "notes-doc min-h-full font-reading text-base leading-relaxed outline-none",
      },
    },
  });

  // Typing can set `dirty` again while a save is in flight, so it is read through a function.
  const pending = () => dirty.current;
  const saveRef = useRef<() => Promise<void>>(() => Promise.resolve());
  const save = useCallback(async (): Promise<void> => {
    if (!pending() || saving.current) return;
    saving.current = true;
    dirty.current = false;
    setState("saving");
    try {
      const saved = await saveNotes(paperId, editor.getJSON() as NotesDoc, version.current);
      version.current = saved.version;
      queryClient.setQueryData(notesKeys.forPaper(paperId), saved);
      setState(pending() ? "saving" : "saved");
    } catch (err) {
      dirty.current = true;
      if (err instanceof NotesChangedError) setState("stale");
      else if (editor.getText().length > MAX_NOTES_CHARS) setState("too-long");
      else {
        setState("error");
        clearTimeout(timer.current);
        timer.current = setTimeout(() => void saveRef.current(), RETRY_AFTER_MS);
      }
      return;
    } finally {
      saving.current = false;
    }
    if (pending()) void saveRef.current(); // typed again while the save was in flight
  }, [editor, paperId, queryClient]);
  useEffect(() => {
    saveRef.current = save;
  }, [save]);

  useEffect(() => {
    const onUpdate = () => {
      dirty.current = true;
      setState((current) => (current === "stale" ? current : "idle"));
      clearTimeout(timer.current);
      timer.current = setTimeout(() => void save(), SAVE_AFTER_MS);
    };
    editor.on("update", onUpdate);
    return () => {
      editor.off("update", onUpdate);
    };
  }, [editor, save]);

  // Leaving the tab or the paper: save what is pending at once.
  useEffect(
    () => () => {
      clearTimeout(timer.current);
      void save();
    },
    [save],
  );

  // Saved elsewhere (Save to notes, another tab) while nothing is pending here: show it.
  const latest = useQuery<Notes>({ queryKey: notesKeys.forPaper(paperId), enabled: false });
  useEffect(() => {
    const next = latest.data;
    if (!next || next.version <= version.current || dirty.current) return;
    version.current = next.version;
    editor.commands.setContent(content(next.doc), { emitUpdate: false });
  }, [latest.data, editor]);

  const reload = async () => {
    const fresh = await getNotes(paperId);
    queryClient.setQueryData(notesKeys.forPaper(paperId), fresh);
    dirty.current = false;
    version.current = fresh.version;
    editor.commands.setContent(content(fresh.doc), { emitUpdate: false });
    setState("idle");
  };
  const keepMine = async () => {
    const fresh = await getNotes(paperId);
    version.current = fresh.version;
    dirty.current = true;
    await save();
  };

  /** A source in a note opens the paper at its page, highlighted (AC2). */
  const openSource = (event: MouseEvent<HTMLDivElement>) => {
    const source = (event.target as HTMLElement).closest<HTMLElement>("[data-source]");
    if (!source || !citations) return;
    const page = Number(source.dataset.page);
    if (page > 0) citations.open(page, source.dataset.quote ?? "");
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex items-center gap-2 border-b border-border pb-2">
        <Toolbar editor={editor} />
        <p aria-live="polite" className="ml-auto shrink-0 text-xs text-text-secondary">
          {STATE_TEXT[state] ?? ""}
        </p>
      </div>
      {state === "stale" && (
        <div role="alert" className="rounded-md border border-border p-3 text-sm">
          These notes changed in another tab.
          <span className="mt-2 flex flex-wrap gap-2">
            <button type="button" onClick={() => void reload()} className="min-h-9 rounded-md border border-border px-3 hover:bg-muted">
              Reload
            </button>
            <button type="button" onClick={() => void keepMine()} className="min-h-9 rounded-md border border-border px-3 hover:bg-muted">
              Keep mine
            </button>
          </span>
        </div>
      )}
      <FieldError
        id="notes-error"
        message={state === "too-long" ? `Notes can be up to ${MAX_NOTES_CHARS.toLocaleString()} characters. Shorten them to save.` : null}
      />
      {/* Reading text keeps a comfortable line length inside its panel (6b). */}
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain" onClick={openSource}>
        <div className="mx-auto h-full max-w-prose py-2">
          <EditorContent editor={editor} className="h-full" />
        </div>
      </div>
    </div>
  );
}
