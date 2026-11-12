import { api, apiBaseUrl } from "@/api/client";
import type { components } from "@/api/schema";
import { currentToken, refreshToken } from "@/auth/session";
import { createSseParser } from "@/features/papers/progress";
import { problem } from "@/lib/problem";

export type Conversation = components["schemas"]["ConversationOut"];
export type Region = components["schemas"]["Region"];
export type Message = components["schemas"]["MessageOut"];
export type Citation = components["schemas"]["CitationOut"];
export type Quote = components["schemas"]["Quote"];

/** What a question is about besides its text: a region (009 AC10) or a quote (015 AC4, AC5). */
export interface Attachment {
  region?: Region | null;
  quote?: Quote | null;
  mode?: "ask" | "explain";
  level?: "plain" | "expert";
}
export const MAX_MESSAGE_CHARS = 4000; // AC16, same as the server

export const chatKeys = {
  conversations: (paperId: string) => ["papers", paperId, "conversations"] as const,
  messages: (conversationId: string) => ["conversations", conversationId, "messages"] as const,
};

export async function listConversations(paperId: string): Promise<Conversation[]> {
  const { data, response } = await api.GET("/api/v1/papers/{paper_id}/conversations", {
    params: { path: { paper_id: paperId } },
  });
  if (!data) throw await problem(response, "Could not load conversations.");
  return data.items;
}

export async function createConversation(paperId: string): Promise<Conversation> {
  const { data, response } = await api.POST("/api/v1/papers/{paper_id}/conversations", {
    params: { path: { paper_id: paperId } },
  });
  if (!data) throw await problem(response, "Could not start a conversation.");
  return data;
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const { response } = await api.DELETE("/api/v1/conversations/{conversation_id}", {
    params: { path: { conversation_id: conversationId } },
  });
  if (!response.ok) throw await problem(response, "Could not delete this conversation.");
}

/** Newest first from the API; returned oldest first for display. */
export async function listMessages(conversationId: string): Promise<Message[]> {
  const { data, response } = await api.GET("/api/v1/conversations/{conversation_id}/messages", {
    params: { path: { conversation_id: conversationId }, query: { limit: 50 } },
  });
  if (!data) throw await problem(response, "Could not load messages.");
  return [...data.items].reverse();
}

export type ChatEvent =
  | { event: "accepted"; data: { conversation_id: string; user_message_id: string } }
  | { event: "status"; data: { step: string; label: string } }
  | { event: "delta"; data: { text: string } }
  | { event: "citations"; data: { items: Citation[] } }
  | {
      event: "done";
      data: { message_id: string; content: string; status: Message["status"]; retrieval_mode: Message["retrieval_mode"]; suggestions?: string[] };
    };

/**
 * Send a question and read the answer stream (fetch-based SSE: the token stays in a header).
 * The Idempotency-Key is created once per question, so a retried request replays the answer.
 */
export async function sendMessage(
  conversationId: string,
  content: string,
  idempotencyKey: string,
  onEvent: (event: ChatEvent) => void,
  signal: AbortSignal,
  attachment: Attachment = {},
): Promise<void> {
  const { region, quote, mode, level } = attachment;
  const body = { content, ...(region ? { region } : {}), ...(quote ? { quote, mode: mode ?? "ask", level: level ?? "plain" } : {}) };
  const send = async (token: string | null) =>
    globalThis.fetch(`${apiBaseUrl}/api/v1/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        "Idempotency-Key": idempotencyKey,
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      signal,
    });
  let response = await send(await currentToken());
  if (response.status === 401) response = await send(await refreshToken());
  if (!response.ok || !response.body) throw await problem(response, "Could not send your question.");
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parse = createSseParser();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    for (const item of parse(value)) {
      const data: unknown = JSON.parse(item.data);
      onEvent({ event: item.event, data } as ChatEvent);
    }
  }
}

/** Spec 015 AC1: questions written for this paper (the generic ones if that failed). */
export async function getSuggestions(paperId: string): Promise<string[]> {
  const { data, response } = await api.GET("/api/v1/papers/{paper_id}/suggestions", {
    params: { path: { paper_id: paperId } },
  });
  if (!data) throw await problem(response, "Could not load suggested questions.");
  return data.questions;
}
