import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { apiBaseUrl } from "@/api/client";
import { currentToken, refreshToken } from "@/auth/session";
import { createSseParser } from "@/features/papers/progress";

import { getSummary, summaryKeys, type Summary } from "./api";

function finished(summary: Summary): boolean {
  return summary.status === "ready" || summary.status === "failed";
}

/** A summary that updates live while it is generated (events stream; polling as fallback). */
export function useSummary(summaryId: string | null) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: summaryKeys.detail(summaryId ?? "none"),
    queryFn: () => getSummary(summaryId ?? ""),
    enabled: summaryId !== null,
    refetchInterval: (q) => (q.state.data && !finished(q.state.data) ? 5000 : false),
  });

  useEffect(() => {
    if (summaryId === null) return;
    const controller = new AbortController();
    const key = summaryKeys.detail(summaryId);
    const run = async () => {
      const send = async (token: string | null) =>
        globalThis.fetch(`${apiBaseUrl}/api/v1/summaries/${encodeURIComponent(summaryId)}/events`, {
          headers: { Accept: "text/event-stream", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          signal: controller.signal,
        });
      let response = await send(await currentToken());
      if (response.status === 401) response = await send(await refreshToken());
      if (!response.ok || !response.body) return; // polling covers it
      const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
      const parse = createSseParser();
      for (;;) {
        const { value, done } = await reader.read();
        if (done) return;
        for (const event of parse(value)) {
          if (event.event !== "summary") continue;
          const summary = JSON.parse(event.data) as Summary;
          queryClient.setQueryData(key, summary);
          if (finished(summary)) void queryClient.invalidateQueries({ queryKey: ["papers"] });
        }
      }
    };
    run().catch(() => undefined); // aborted or network: the polling fallback continues
    return () => {
      controller.abort();
    };
  }, [summaryId, queryClient]);

  return query;
}
