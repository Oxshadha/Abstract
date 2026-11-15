import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, BookOpen, Check, ChevronDown, FileText, Loader2, MessageSquareQuote, NotebookPen, Plus, RotateCcw, Sparkles, Square, SquareDashedMousePointer, User, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { StatusPill } from "@/components/status/StatusPill";
import { toast } from "@/components/status/toast";
import { getStatus, paperKeys } from "@/features/papers/api";
import { useFlag } from "@/features/flags/api";
import { notesKeys, saveAnswer } from "@/features/notes/api";
import { Markdown } from "@/features/summaries/Markdown";

import {
  MAX_MESSAGE_CHARS,
  chatKeys,
  createConversation,
  getSuggestions,
  listConversations,
  listMessages,
  type Citation,
  type Attachment,
  type Conversation,
  type Message,
  type Quote,
  type Region,
} from "./api";
import { useCitations } from "@/features/viewer/citation-context";
import { Dictation } from "@/features/voice/Dictation";
import { countDictation, useCanListen, useCanSpeak } from "@/features/voice/hooks";
import { ListenControls } from "@/features/voice/ListenControls";

import { withMarkers } from "./markers";
import { completedSentences, useChat, type Draft } from "./useChat";

const EXAMPLES = [
  "What problem does this paper address?",
  "How does the proposed method work?",
  "What are the main results?",
];
const EXPLAIN = {
  plain: "Explain this passage in plain words.",
  expert: "Explain this passage for a researcher in the field.",
} as const;

function citationLabel(c: Citation): string {
  const pages =
    c.page_start == null ? "" : c.page_end != null && c.page_end !== c.page_start ? `p. ${String(c.page_start)}-${String(c.page_end)}` : `p. ${String(c.page_start)}`;
  // A table or figure reads like the paper names it (spec 009 AC9): "[2] Table 2, p. 8".
  if (c.element) return `[${String(c.marker)}] ${c.element.label}, ${pages}`;
  if (c.region) return `[${String(c.marker)}] Region, ${pages}`;
  const section = c.section && !/front matter/i.test(c.section) ? ` (${c.section.slice(0, 28)})` : "";
  return `[${String(c.marker)}] ${pages}${section}`;
}

function Citations({ items }: { items: Citation[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const viewer = useCitations();
  if (items.length === 0) return null;
  const current = items.find((c) => c.marker === open);
  return (
    <div className="mt-2 flex flex-col gap-2">
      <div className="flex flex-wrap gap-1.5">
        {items.map((c) => (
          <button
            key={c.marker}
            type="button"
            aria-expanded={open === c.marker}
            onClick={() => {
              setOpen(open === c.marker ? null : c.marker);
              // Spec 008 AC4: open the cited page with the sentence highlighted.
              if (c.page_start != null && open !== c.marker) {
                // A table or figure is outlined in the paper; a passage highlights its sentence.
                if (c.element) viewer?.openBox(c.page_start, c.element.box, c.element.label);
                else if (c.region) viewer?.openBox(c.page_start, c.region, "the selected region");
                else viewer?.open(c.page_start, c.quote);
              }
            }}
            className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-border px-2 text-sm hover:bg-muted"
          >
            <BookOpen aria-hidden className="size-4" />
            {citationLabel(c)}
          </button>
        ))}
      </div>
      {current && current.quote && (
        <blockquote className="rounded-md bg-muted p-2.5 font-reading text-sm">
          <q>{current.quote}</q>
        </blockquote>
      )}
    </div>
  );
}

/** A region of a page (spec 009 AC10): opens the box in the paper; removable while composing. */
function RegionChip({ region, onRemove }: { region: Region; onRemove?: () => void }) {
  const viewer = useCitations();
  const label = `Region, p. ${String(region.page)}`;
  return (
    <span className="inline-flex items-center rounded-md border border-border bg-surface text-sm">
      <button
        type="button"
        onClick={() => { viewer?.openBox(region.page, region, "the selected region"); }}
        className="inline-flex min-h-9 items-center gap-1.5 px-2 hover:bg-muted"
      >
        <SquareDashedMousePointer aria-hidden className="size-4" />
        {label}
      </button>
      {onRemove && (
        <button type="button" aria-label={`Remove ${label}`} onClick={onRemove} className="inline-flex size-9 items-center justify-center hover:bg-muted">
          <X aria-hidden className="size-3.5" />
        </button>
      )}
    </span>
  );
}

/** Text selected in the paper (spec 015 AC5): opens it highlighted; removable while composing. */
function QuoteChip({ quote, trimmed, onRemove }: { quote: Quote; trimmed?: boolean; onRemove?: () => void }) {
  const viewer = useCitations();
  const page = `p. ${String(quote.page)}`;
  return (
    <span className="flex w-full min-w-0 items-start rounded-md border border-border bg-surface text-sm">
      <button
        type="button"
        aria-label={`Quote from ${page}: ${quote.text.slice(0, 80)}`}
        onClick={() => { viewer?.open(quote.page, quote.text); }}
        className="flex min-h-9 min-w-0 flex-1 items-start gap-1.5 px-2 py-1.5 text-left hover:bg-muted"
      >
        <MessageSquareQuote aria-hidden className="mt-0.5 size-4 shrink-0" />
        <span className="min-w-0 flex-1">
          <span className="line-clamp-2 font-reading">{quote.text}</span>
          <span className="text-xs text-text-secondary">{trimmed ? `${page}, trimmed to 1,000 characters` : page}</span>
        </span>
      </button>
      {onRemove && (
        <button type="button" aria-label="Remove quote" onClick={onRemove} className="inline-flex size-9 shrink-0 items-center justify-center hover:bg-muted">
          <X aria-hidden className="size-3.5" />
        </button>
      )}
    </span>
  );
}

function Attached({ region, quote }: { region?: Region | null; quote?: Quote | null }) {
  if (region) return <span className="mb-1.5 block"><RegionChip region={region} /></span>;
  if (quote) return <span className="mb-1.5 block"><QuoteChip quote={quote} /></span>;
  return null;
}

function Bubble({ role, children }: { role: Message["role"]; children: ReactNode }) {
  if (role === "user") {
    return (
      <div className="flex items-start justify-end gap-2">
        <div className="max-w-[85%] rounded-lg bg-muted px-3 py-2">{children}</div>
        <User aria-hidden className="mt-1 size-5 shrink-0 text-text-secondary" />
      </div>
    );
  }
  return (
    <div className="flex items-start gap-2">
      <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md border border-border">
        <FileText aria-hidden className="size-4" />
      </span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

/**
 * The newest message is a question with no answer yet, asked in the last few minutes: the
 * server is still writing it (the reader left mid-answer and came back).
 */
function awaitingAnswer(items: Message[] | undefined): boolean {
  const last = items?.[items.length - 1];
  if (last?.role !== "user") return false;
  return Date.now() - new Date(last.created_at).getTime() < 3 * 60_000;
}

/** Spec 014 AC2: add this answer, with its question and page sources, to the paper's notes. */
function SaveToNotes({ paperId, messageId, saved }: { paperId: string; messageId: string; saved: boolean }) {
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: () => saveAnswer(paperId, messageId),
    onSuccess: (notes) => {
      queryClient.setQueryData(notesKeys.forPaper(paperId), notes);
      // The server remembers it on the message, so the button stays Saved after a reload.
      void queryClient.invalidateQueries({ queryKey: ["conversations"] });
      toast("Saved to your notes.");
    },
    onError: (err) => {
      toast(err.message);
    },
  });
  const done = saved || save.isSuccess;
  return (
    <button
      type="button"
      disabled={save.isPending || done}
      onClick={() => { save.mutate(); }}
      className="mt-2 inline-flex min-h-9 items-center gap-1.5 rounded-md px-2 text-sm text-text-secondary hover:bg-muted hover:text-text disabled:opacity-60"
    >
      {done ? <Check aria-hidden className="size-4" /> : <NotebookPen aria-hidden className="size-4" />}
      {save.isPending ? "Saving" : done ? "Saved to notes" : "Save to notes"}
    </button>
  );
}

function AssistantMessage({ message, paperId, notes }: { message: Message; paperId: string; notes: boolean }) {
  const canListen = useCanListen();
  return (
    <Bubble role="assistant">
      {message.status === "stopped" && <StatusPill status="neutral">Stopped</StatusPill>}
      {message.retrieval_mode === "keyword" && <StatusPill status="neutral">Answered from a keyword search</StatusPill>}
      <Markdown>{withMarkers(message.content)}</Markdown>
      <Citations items={message.citations} />
      {message.content.trim() && (notes || canListen) && (
        <span className="flex flex-wrap items-center gap-2">
          {notes && <SaveToNotes paperId={paperId} messageId={message.id} saved={message.saved_to_notes} />}
          {/* Spec 020 AC5b: read this answer aloud, without markers or chips (AC5c). */}
          {canListen && <ListenControls owner={`answer:${message.id}`} variant="answer" segments={() => [{ key: "answer", text: message.content }]} />}
        </span>
      )}
    </Bubble>
  );
}

function Pending({ draft, onRetry }: { draft: Draft; onRetry: () => void }) {
  return (
    <>
      <Bubble role="user">
        <Attached region={draft.attachment.region} quote={draft.attachment.quote} />
        {draft.question}
      </Bubble>
      <Bubble role="assistant">
        {draft.status === "failed" ? (
          <div className="flex flex-col items-start gap-2">
            <p>{draft.error ?? "Something went wrong."}</p>
            <button type="button" onClick={onRetry} className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-border px-3 hover:bg-muted">
              <RotateCcw aria-hidden className="size-4" />
              Retry
            </button>
          </div>
        ) : (
          <>
            {draft.activity && (
              <p className="mb-1 flex items-center gap-2 text-sm text-text-secondary">
                <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" />
                {draft.activity}
              </p>
            )}
            {draft.text && <Markdown>{withMarkers(draft.text)}</Markdown>}
            <Citations items={draft.citations} />
          </>
        )}
      </Bubble>
    </>
  );
}

function ConversationSwitcher({
  conversations,
  current,
  onSelect,
  onNew,
}: {
  conversations: Conversation[];
  current: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const [open, setOpen] = useState(false);
  const title = conversations.find((c) => c.id === current)?.title ?? "New conversation";
  return (
    <div className="relative min-w-0">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
        }}
        className="inline-flex min-h-11 max-w-full items-center gap-1.5 rounded-md px-2 text-sm text-text-secondary hover:bg-muted"
      >
        <span className="truncate">{title}</span>
        <ChevronDown aria-hidden className="size-4 shrink-0" />
      </button>
      {open && (
        <ul role="listbox" aria-label="Conversations" className="absolute left-0 z-20 mt-1 max-h-72 w-72 overflow-auto rounded-lg border border-border bg-surface p-1 shadow-overlay">
          <li>
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                onNew();
              }}
              className="flex w-full items-center gap-2 rounded-md p-2 text-left font-medium hover:bg-muted"
            >
              <Plus aria-hidden className="size-4" />
              New conversation
            </button>
          </li>
          {conversations.map((c) => (
            <li key={c.id} role="option" aria-selected={c.id === current}>
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  onSelect(c.id);
                }}
                className="w-full truncate rounded-md p-2 text-left text-sm hover:bg-muted"
              >
                {c.title}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Ask Abstract (spec 007 AC9, AC10, AC14 to AC16), opened on demand in the Workspace (D79). */
export function ChatPanel({ paperId, onClose }: { paperId: string; onClose?: () => void }) {
  const queryClient = useQueryClient();
  const notes = useFlag("notes");
  const inputId = useId();
  const viewerApi = useCitations(); // a region waiting to be asked about (spec 009 AC10)
  const status = useQuery({ queryKey: paperKeys.status(paperId), queryFn: () => getStatus(paperId),
    refetchInterval: (q) => (q.state.data?.chat_available ? false : 3000) });
  const available = status.data?.chat_available === true;
  const conversations = useQuery({ queryKey: chatKeys.conversations(paperId), queryFn: () => listConversations(paperId), enabled: available });
  const [chosen, setChosen] = useState<string | null>(null);
  const conversationId = chosen ?? conversations.data?.[0]?.id ?? null;
  // Sending before the list has loaded would start a second conversation, and switching to the
  // loaded one would cancel the answer: wait until we know which conversation is current.
  const ready = available && !conversations.isPending;
  const messages = useQuery({
    queryKey: chatKeys.messages(conversationId ?? "none"),
    queryFn: () => listMessages(conversationId ?? ""),
    enabled: conversationId !== null,
    // Back after leaving mid-answer: the server is still writing it, so look again until it lands.
    refetchInterval: (q) => (awaitingAnswer(q.state.data) ? 3000 : false),
  });
  const { draft, send, stop, busy, suggestions, retry } = useChat(conversationId);
  const [input, setInput] = useState("");
  // Spec 020: what was typed before speaking, and what was dictated (to count edits, AC9).
  const typedBefore = useRef("");
  const dictated = useRef<string | null>(null);
  const canSpeak = useCanSpeak();
  const withTyped = (text: string) => (typedBefore.current ? `${typedBefore.current} ${text}` : text);
  const end = useRef<HTMLDivElement>(null);
  const pendingQuestion = useRef<{ text: string; attachment: Attachment } | null>(null);
  // Spec 015 AC1: questions written for this paper, the generic ones until they arrive.
  const suggested = useQuery({ queryKey: ["papers", paperId, "suggestions"], queryFn: () => getSuggestions(paperId), enabled: available, staleTime: Infinity, retry: false });
  const starters = suggested.data ?? (suggested.isError ? EXAMPLES : []);

  const create = useMutation({
    mutationFn: () => createConversation(paperId),
    onSuccess: async (conversation) => {
      await queryClient.invalidateQueries({ queryKey: chatKeys.conversations(paperId) });
      setChosen(conversation.id);
    },
  });

  useEffect(() => {
    const el = end.current as Partial<HTMLDivElement> | null;
    el?.scrollIntoView?.({ block: "end" }); // absent in some test browsers
  }, [messages.data, draft?.text, draft?.activity]);

  /** The region or Ask quote waiting in the composer, taken off it as the question is sent. */
  const takeAttachment = (): Attachment => {
    const quote = viewerApi?.quote;
    const attachment: Attachment = viewerApi?.region
      ? { region: viewerApi.region }
      : quote?.mode === "ask"
        ? { quote: { page: quote.page, text: quote.text }, mode: "ask" }
        : {};
    viewerApi?.clearRegion();
    if (quote?.mode === "ask") viewerApi?.clearQuote();
    return attachment;
  };
  const submit = async (text: string, attached: Attachment) => {
    if (!conversationId) {
      // Queue first: the hook re-binds to the new conversation on the next render, then sends.
      pendingQuestion.current = { text, attachment: attached };
      try {
        const conversation = await create.mutateAsync();
        setChosen(conversation.id);
      } catch {
        // Never lose the question: put it back and say what happened.
        pendingQuestion.current = null;
        if (!attached.quote || attached.mode !== "explain") setInput((current) => current || text);
        toast("Could not start a conversation. Your question is still here, try again.");
      }
      return;
    }
    await send(text, undefined, attached);
  };
  const ask = async (question: string) => {
    const text = question.trim().slice(0, MAX_MESSAGE_CHARS);
    if (!text || busy) return;
    countDictation(dictated.current, text);
    dictated.current = null;
    setInput("");
    await submit(text, takeAttachment());
  };
  useEffect(() => {
    if (conversationId && pendingQuestion.current) {
      const { text, attachment } = pendingQuestion.current;
      pendingQuestion.current = null;
      void send(text, undefined, attachment);
    }
  }, [conversationId, send]);
  // Spec 015 AC4: Explain asks at once, at the level chosen in the toolbar.
  const explain = viewerApi?.quote?.mode === "explain" ? viewerApi.quote : null;
  useEffect(() => {
    if (!explain || !ready || busy || create.isPending) return;
    viewerApi?.clearQuote();
    // The request comes from the Paper panel through context (the chat may only just have
    // opened for it), so sending it is this effect's job, once per request id.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void submit(EXPLAIN[explain.level], { quote: { page: explain.page, text: explain.text }, mode: "explain", level: explain.level });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [explain?.id, ready, busy]);

  const onKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault(); // Enter sends; Shift+Enter adds a new line
      void ask(input);
    }
  };

  const items = messages.data ?? [];
  const empty = items.length === 0 && !draft;
  const writing = !draft && awaitingAnswer(messages.data);
  // Follow-ups after an answer: the ones it came with, otherwise this paper's questions not asked
  // yet, so suggestions stay after a reload or a return visit instead of disappearing.
  const asked = new Set(items.filter((m) => m.role === "user").map((m) => m.content.trim()));
  const followUps = (suggestions.length > 0 ? suggestions : starters.filter((q) => !asked.has(q.trim()))).slice(0, 3);

  return (
    <div className="flex h-full min-h-96 flex-col">
      <div className="flex items-center gap-2">
        <Sparkles aria-hidden className="size-5" />
        <h2 className="font-display text-lg font-bold whitespace-nowrap">Ask Abstract</h2>
        {available && (conversations.data?.length ?? 0) > 0 && (
          <ConversationSwitcher
            conversations={conversations.data ?? []}
            current={conversationId}
            onSelect={setChosen}
            onNew={() => {
              create.mutate();
            }}
          />
        )}
        {onClose && (
          <button type="button" aria-label="Close chat" onClick={onClose} className="ml-auto inline-flex size-11 items-center justify-center rounded-md hover:bg-muted">
            <X aria-hidden className="size-5" />
          </button>
        )}
      </div>

      <div className="mt-3 flex min-h-0 flex-1 flex-col gap-4 overflow-auto" role="log" aria-label="Conversation">
        {!available ? (
          <p className="text-sm text-text-secondary">Chat opens as soon as the paper is indexed. This takes a few seconds.</p>
        ) : empty ? (
          <div className="flex flex-col items-start gap-2">
            <p className="text-sm text-text-secondary">Ask anything about this paper. Answers come only from the paper, with sources.</p>
            {starters.map((q) => (
              <button key={q} type="button" disabled={!ready} onClick={() => void ask(q)} className="w-full rounded-lg border border-border bg-surface px-3.5 py-2.5 text-left text-sm leading-snug hover:bg-muted disabled:opacity-50">
                {q}
              </button>
            ))}
          </div>
        ) : (
          items.map((m) =>
            m.role === "user" ? (
              <Bubble key={m.id} role="user">
                <Attached region={m.region} quote={m.quote} />
                {m.content}
              </Bubble>
            ) : (
              <AssistantMessage key={m.id} message={m} paperId={paperId} notes={notes} />
            ),
          )
        )}
        {draft && <Pending draft={draft} onRetry={() => void retry(draft)} />}
        {writing && (
          <p role="status" className="inline-flex items-center gap-2 text-sm text-text-secondary">
            <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" />
            Writing the answer
          </p>
        )}
        {!empty && followUps.length > 0 && !draft && (
          <div className="flex flex-col items-start gap-2" aria-label="Suggested questions" role="group">
            {followUps.map((q) => (
              <button key={q} type="button" disabled={!ready} onClick={() => void ask(q)} className="max-w-full rounded-lg border border-border bg-surface px-3.5 py-2 text-left text-sm leading-snug hover:bg-muted disabled:opacity-50">
                {q}
              </button>
            ))}
          </div>
        )}
        <div ref={end} />
      </div>
      {/* AC15: announce completed sentences, not every token. */}
      <p className="sr-only" aria-live="polite">{draft ? completedSentences(draft.text) : ""}</p>

      <form
        className="mt-3 flex flex-wrap items-end gap-2 rounded-lg border border-border p-2"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(input);
        }}
      >
        {viewerApi?.region && (
          <span className="basis-full pb-1">
            <RegionChip region={viewerApi.region} onRemove={viewerApi.clearRegion} />
          </span>
        )}
        {viewerApi?.quote?.mode === "ask" && (
          <span className="basis-full pb-1">
            <QuoteChip quote={viewerApi.quote} trimmed={viewerApi.quote.trimmed} onRemove={viewerApi.clearQuote} />
          </span>
        )}
        <Dictation
          paperId={paperId}
          disabled={!ready || busy}
          onStart={() => { typedBefore.current = input.trim(); }}
          onDictated={(text) => { dictated.current = withTyped(text); }}
          onReview={(text) => { setInput(withTyped(text)); }}
          onSend={(text) => { void ask(withTyped(text)); }}
        >
          {(mic) => (
            <>
        <label htmlFor={inputId} className="sr-only">Ask about this paper</label>
        <textarea
          id={inputId}
          value={input}
          disabled={!ready}
          maxLength={MAX_MESSAGE_CHARS}
          rows={Math.min(6, Math.max(1, input.split("\n").length))}
          placeholder={!available ? "Waiting for the paper to be indexed" : viewerApi?.quote?.mode === "ask" ? "Ask about this passage" : "Ask about this paper"}
          onChange={(e) => {
            setInput(e.target.value);
          }}
          onKeyDown={onKey}
          className="min-h-11 flex-1 resize-none bg-transparent px-2 py-2.5 font-reading focus:outline-none"
        />
        {busy ? (
          <button type="button" aria-label="Stop" onClick={stop} className="inline-flex size-11 items-center justify-center rounded-md bg-primary text-primary-text hover:opacity-90">
            <Square aria-hidden className="size-3.5 fill-current" />
          </button>
        ) : (
          <>
            {canSpeak && mic}
            <button type="submit" aria-label="Send" disabled={!ready || !input.trim()} className="inline-flex size-11 items-center justify-center rounded-md bg-primary text-primary-text disabled:opacity-50">
              <ArrowUp aria-hidden className="size-5" />
            </button>
          </>
        )}
            </>
          )}
        </Dictation>
      </form>
      {input.length > MAX_MESSAGE_CHARS - 200 && (
        <p className="mt-1 text-right text-xs text-text-secondary">{`${String(input.length)} / ${String(MAX_MESSAGE_CHARS)}`}</p>
      )}
    </div>
  );
}
