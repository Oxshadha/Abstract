import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { chatKeys, sendMessage, type Citation, type Message, type Region } from "./api";

export interface Draft {
  question: string;
  text: string;
  activity: string | null;
  citations: Citation[];
  status: "streaming" | "failed";
  error?: string;
  idempotencyKey: string;
  region?: Region | null; // Ask about this region (spec 009 AC10)
}

/** Completed sentences only, for the live region (AC15): never every token. */
export function completedSentences(text: string): string {
  const match = /^[\s\S]*[.!?](?=\s|$)/.exec(text);
  return match ? match[0] : "";
}

/**
 * One question at a time per conversation. Tokens are buffered and flushed once per animation
 * frame (AC15); switching conversation or paper aborts the stream, and events from an old stream
 * are ignored (AC14).
 */
export function useChat(conversationId: string | null) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const controller = useRef<AbortController | null>(null);
  const active = useRef(conversationId);
  const buffer = useRef("");
  const frame = useRef<number | null>(null);

  useEffect(() => {
    active.current = conversationId;
    return () => {
      controller.current?.abort(); // AC14: leaving the conversation stops its stream
      controller.current = null;
      setDraft(null);
    };
  }, [conversationId]);

  const flush = useCallback(() => {
    frame.current = null;
    const text = buffer.current;
    buffer.current = "";
    if (text) setDraft((d) => (d ? { ...d, text: d.text + text } : d));
  }, []);

  const send = useCallback(
    async (question: string, idempotencyKey: string = crypto.randomUUID(), region: Region | null = null) => {
      if (!conversationId) return;
      const target = conversationId;
      const abort = new AbortController();
      controller.current = abort;
      setSuggestions([]);
      setDraft({ question, text: "", activity: null, citations: [], status: "streaming", idempotencyKey, region });
      const mine = () => active.current === target && controller.current === abort; // AC14
      try {
        await sendMessage(
          target,
          question,
          idempotencyKey,
          (event) => {
            if (!mine()) return;
            if (event.event === "accepted" && event.data.conversation_id !== target) return;
            if (event.event === "status") setDraft((d) => (d ? { ...d, activity: event.data.label } : d));
            if (event.event === "delta") {
              buffer.current += event.data.text;
              frame.current ??= requestAnimationFrame(flush);
            }
            if (event.event === "citations") setDraft((d) => (d ? { ...d, citations: event.data.items } : d));
            if (event.event === "done") {
              setSuggestions(event.data.suggestions ?? []);
            }
          },
          abort.signal,
          region,
        );
        if (!mine()) return;
        await queryClient.invalidateQueries({ queryKey: chatKeys.messages(target) });
        void queryClient.invalidateQueries({ queryKey: ["papers"] });
        setDraft(null);
      } catch (err) {
        if (abort.signal.aborted) {
          // Stopped by the user: the server saved the partial answer as stopped (AC13).
          await queryClient.invalidateQueries({ queryKey: chatKeys.messages(target) });
          if (mine()) setDraft(null);
          return;
        }
        if (mine()) {
          setDraft((d) => (d ? { ...d, status: "failed", error: err instanceof Error ? err.message : "Something went wrong." } : d));
        }
      } finally {
        if (frame.current !== null) cancelAnimationFrame(frame.current);
        frame.current = null;
        buffer.current = "";
        if (controller.current === abort) controller.current = null;
      }
    },
    [conversationId, flush, queryClient],
  );

  const stop = useCallback(() => {
    controller.current?.abort();
  }, []);

  const busy = draft?.status === "streaming";
  return { draft, send, stop, busy, suggestions, retry: (d: Draft) => send(d.question, d.idempotencyKey, d.region ?? null) };
}

export type { Message };
