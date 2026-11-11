import { api, apiBaseUrl } from "@/api/client";
import type { components } from "@/api/schema";
import { currentToken, refreshToken } from "@/auth/session";
import { createSseParser } from "@/features/papers/progress";
import { HttpError } from "@/lib/queryClient";

export type Conversation = components["schemas"]["ConversationOut"];
export type Message = components["schemas"]["MessageOut"];
export type Citation = components["schemas"]["CitationOut"];
export const MAX_MESSAGE_CHARS = 4000; // AC16, same as the server

export const chatKeys = {
  conversations: (paperId: string) => ["papers", paperId, "conversations"] as const,
  messages: (conversationId: string) => ["conversations", conversationId, "messages"] as const,
};

async function problem(response: Response, fallback: string): Promise<HttpError> {
  try {
    const body = (await response.clone().json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail) return new HttpError(response.status, body.detail);
  } catch {
    // not JSON
  }
  return new HttpError(response.status, fallback);
}

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
): Promise<void> {
  const send = async (token: string | null) =>
    globalThis.fetch(`${apiBaseUrl}/api/v1/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        "Idempotency-Key": idempotencyKey,
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ content }),
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
