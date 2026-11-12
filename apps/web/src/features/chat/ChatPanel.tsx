import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, BookOpen, ChevronDown, FileText, Loader2, Plus, RotateCcw, Sparkles, Square, User, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { StatusPill } from "@/components/status/StatusPill";
import { getStatus, paperKeys } from "@/features/papers/api";
import { Markdown } from "@/features/summaries/Markdown";

import {
  MAX_MESSAGE_CHARS,
  chatKeys,
  createConversation,
  listConversations,
  listMessages,
  type Citation,
  type Conversation,
  type Message,
} from "./api";
import { useCitations } from "@/features/viewer/citation-context";

import { withMarkers } from "./markers";
import { completedSentences, useChat, type Draft } from "./useChat";

const EXAMPLES = [
  "What problem does this paper address?",
  "How does the proposed method work?",
  "What are the main results?",
];

function citationLabel(c: Citation): string {
  const pages =
    c.page_start == null ? "" : c.page_end != null && c.page_end !== c.page_start ? `p. ${String(c.page_start)}-${String(c.page_end)}` : `p. ${String(c.page_start)}`;
  // A table or figure reads like the paper names it (spec 009 AC9): "[2] Table 2, p. 8".
  if (c.element) return `[${String(c.marker)}] ${c.element.label}, ${pages}`;
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

function AssistantMessage({ message }: { message: Message }) {
  return (
    <Bubble role="assistant">
      {message.status === "stopped" && <StatusPill status="neutral">Stopped</StatusPill>}
      {message.retrieval_mode === "keyword" && <StatusPill status="neutral">Answered from a keyword search</StatusPill>}
      <Markdown>{withMarkers(message.content)}</Markdown>
      <Citations items={message.citations} />
    </Bubble>
  );
}

function Pending({ draft, onRetry }: { draft: Draft; onRetry: () => void }) {
  return (
    <>
      <Bubble role="user">{draft.question}</Bubble>
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
  const inputId = useId();
  const status = useQuery({ queryKey: paperKeys.status(paperId), queryFn: () => getStatus(paperId),
    refetchInterval: (q) => (q.state.data?.chat_available ? false : 3000) });
  const available = status.data?.chat_available === true;
  const conversations = useQuery({ queryKey: chatKeys.conversations(paperId), queryFn: () => listConversations(paperId), enabled: available });
  const [chosen, setChosen] = useState<string | null>(null);
  const conversationId = chosen ?? conversations.data?.[0]?.id ?? null;
  const messages = useQuery({
    queryKey: chatKeys.messages(conversationId ?? "none"),
    queryFn: () => listMessages(conversationId ?? ""),
    enabled: conversationId !== null,
  });
  const { draft, send, stop, busy, suggestions, retry } = useChat(conversationId);
  const [input, setInput] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const pendingQuestion = useRef<string | null>(null);

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

  const ask = async (question: string) => {
    const text = question.trim().slice(0, MAX_MESSAGE_CHARS);
    if (!text || busy) return;
    setInput("");
    if (!conversationId) {
      // Queue first: the hook re-binds to the new conversation on the next render, then sends.
      pendingQuestion.current = text;
      const conversation = await create.mutateAsync();
      setChosen(conversation.id);
      return;
    }
    await send(text);
  };
  useEffect(() => {
    if (conversationId && pendingQuestion.current) {
      const text = pendingQuestion.current;
      pendingQuestion.current = null;
      void send(text);
    }
  }, [conversationId, send]);

  const onKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault(); // Enter sends; Shift+Enter adds a new line
      void ask(input);
    }
  };

  const items = messages.data ?? [];
  const empty = items.length === 0 && !draft;

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
            {EXAMPLES.map((q) => (
              <button key={q} type="button" onClick={() => void ask(q)} className="min-h-9 rounded-md border border-border px-3 text-left text-sm hover:bg-muted">
                {q}
              </button>
            ))}
          </div>
        ) : (
          items.map((m) =>
            m.role === "user" ? (
              <Bubble key={m.id} role="user">{m.content}</Bubble>
            ) : (
              <AssistantMessage key={m.id} message={m} />
            ),
          )
        )}
        {draft && <Pending draft={draft} onRetry={() => void retry(draft)} />}
        {suggestions.length > 0 && !draft && (
          <div className="flex flex-wrap gap-2">
            {suggestions.map((q) => (
              <button key={q} type="button" onClick={() => void ask(q)} className="min-h-9 rounded-md border border-border px-3 text-sm hover:bg-muted">
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
        className="mt-3 flex items-end gap-2 rounded-lg border border-border p-2"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(input);
        }}
      >
        <label htmlFor={inputId} className="sr-only">Ask about this paper</label>
        <textarea
          id={inputId}
          value={input}
          disabled={!available}
          maxLength={MAX_MESSAGE_CHARS}
          rows={Math.min(6, Math.max(1, input.split("\n").length))}
          placeholder={available ? "Ask about this paper" : "Waiting for the paper to be indexed"}
          onChange={(e) => {
            setInput(e.target.value);
          }}
          onKeyDown={onKey}
          className="min-h-11 flex-1 resize-none bg-transparent px-2 py-2.5 font-reading focus:outline-none"
        />
        {busy ? (
          <button type="button" aria-label="Stop" onClick={stop} className="inline-flex size-11 items-center justify-center rounded-md border border-border hover:bg-muted">
            <Square aria-hidden className="size-4" />
          </button>
        ) : (
          <button type="submit" aria-label="Send" disabled={!available || !input.trim()} className="inline-flex size-11 items-center justify-center rounded-md bg-primary text-primary-text disabled:opacity-50">
            <ArrowUp aria-hidden className="size-5" />
          </button>
        )}
      </form>
      {input.length > MAX_MESSAGE_CHARS - 200 && (
        <p className="mt-1 text-right text-xs text-text-secondary">{`${String(input.length)} / ${String(MAX_MESSAGE_CHARS)}`}</p>
      )}
    </div>
  );
}
