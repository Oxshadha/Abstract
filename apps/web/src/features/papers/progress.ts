import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { apiBaseUrl } from "@/api/client";
import { currentToken, refreshToken } from "@/auth/session";

import { getStatus, paperKeys, type PaperStatus } from "./api";

export interface SseEvent {
  id: string | null;
  event: string;
  data: string;
}

/** Incremental text/event-stream parser: feed chunks, get complete events back. */
export function createSseParser(): (chunk: string) => SseEvent[] {
  let buffer = "";
  return (chunk) => {
    buffer += chunk.replace(/\r\n?/g, "\n");
    const events: SseEvent[] = [];
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let id: string | null = null;
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (!line || line.startsWith(":")) continue; // comments are heartbeats
        const colon = line.indexOf(":");
        const field = colon === -1 ? line : line.slice(0, colon);
        const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
        if (field === "id") id = value;
        else if (field === "event") event = value;
        else if (field === "data") data.push(value);
      }
      if (data.length) events.push({ id, event, data: data.join("\n") });
      boundary = buffer.indexOf("\n\n");
    }
    return events;
  };
}

export function isFinished(status: PaperStatus): boolean {
  return (status.status === "ready" || status.status === "failed") &&
    status.steps.every((s) => s.state === "done" || s.state === "failed");
}

/**
 * Reads the progress stream with fetch (the token goes in a header, never in the URL, AC12).
 * Resolves when the stream ends; rejects on HTTP or network errors. Returns the last event id.
 */
export async function readProgressStream(
  paperId: string,
  lastEventId: string | null,
  onStatus: (status: PaperStatus) => void,
  signal: AbortSignal,
): Promise<string | null> {
  const send = async (token: string | null) =>
    globalThis.fetch(`${apiBaseUrl}/api/v1/papers/${encodeURIComponent(paperId)}/events`, {
      headers: {
        Accept: "text/event-stream",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
      },
      signal,
    });
  let response = await send(await currentToken());
  if (response.status === 401) response = await send(await refreshToken());
  if (!response.ok || !response.body) throw new Error(`progress stream ${String(response.status)}`);
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parse = createSseParser();
  let last = lastEventId;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return last;
    for (const event of parse(value)) {
      if (event.event !== "status") continue;
      last = event.id ?? last;
      onStatus(JSON.parse(event.data) as PaperStatus);
    }
  }
}

const POLL_MS = 3000;
const MAX_STREAM_FAILURES = 3;

/**
 * Live processing status (AC12): the event stream keeps the query cache fresh; after repeated
 * stream failures (proxies, old browsers) the query falls back to polling the status endpoint.
 */
export function useProcessingStatus(paperId: string) {
  const queryClient = useQueryClient();
  const [polling, setPolling] = useState(false);
  const query = useQuery({
    queryKey: paperKeys.status(paperId),
    queryFn: () => getStatus(paperId),
    refetchInterval: (q) => (polling && q.state.data && !isFinished(q.state.data) ? POLL_MS : false),
  });

  useEffect(() => {
    const key = paperKeys.status(paperId);
    const controller = new AbortController();
    const stopped = () => controller.signal.aborted;
    const onStatus = (status: PaperStatus) => {
      queryClient.setQueryData(key, status);
      if (isFinished(status)) void queryClient.invalidateQueries({ queryKey: paperKeys.list });
    };
    const run = async () => {
      let failures = 0;
      let lastId: string | null = null;
      while (failures < MAX_STREAM_FAILURES) {
        try {
          lastId = await readProgressStream(paperId, lastId, onStatus, controller.signal);
          failures = 0;
          const current = queryClient.getQueryData<PaperStatus>(key);
          if (current && isFinished(current)) return;
        } catch {
          failures += 1;
        }
        if (stopped()) return;
        await new Promise((resolve) => setTimeout(resolve, 500 * 2 ** failures));
        if (stopped()) return;
      }
      setPolling(true); // stream unavailable: poll instead
    };
    void run();
    return () => {
      controller.abort();
    };
  }, [paperId, queryClient]);

  return query;
}
