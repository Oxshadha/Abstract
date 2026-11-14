import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { configureAuth } from "@/auth/session";
import { getStatus } from "@/features/papers/api";
import { status } from "@/features/papers/fixtures";
import { seriousViolations } from "@/test/axe";
import { saveAnswer } from "@/features/notes/api";

import { createConversation, getSuggestions, listConversations, listMessages, type Message } from "./api";
import { useCitations } from "@/features/viewer/citation-context";
import { CitationProvider } from "@/features/viewer/citations";

import { ChatPanel } from "./ChatPanel";
import { withMarkers } from "./markers";
import { completedSentences } from "./useChat";

vi.mock("@/features/papers/api", async (orig) => ({ ...(await orig<typeof import("@/features/papers/api")>()), getStatus: vi.fn() }));
vi.mock("@/features/notes/api", async (orig) => ({ ...(await orig<typeof import("@/features/notes/api")>()), saveAnswer: vi.fn() }));
vi.mock("./api", async (orig) => ({
  ...(await orig<typeof import("./api")>()),
  listConversations: vi.fn(), createConversation: vi.fn(), listMessages: vi.fn(), getSuggestions: vi.fn(),
}));

const READY = status({ status: "ready", text_status: "ready", chat_available: true });
const CONVERSATION = { id: "c1", paper_id: "p1", title: "Attention", created_at: "", updated_at: "" };

function sse(events: [string, unknown][], hold = false): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const [name, data] of events) controller.enqueue(encoder.encode(`event: ${name}\ndata: ${JSON.stringify(data)}\n\n`));
      if (!hold) controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

const ANSWER: [string, unknown][] = [
  ["accepted", { conversation_id: "c1", user_message_id: "u1" }],
  ["status", { step: "searching", label: "Searching the paper" }],
  ["delta", { text: "Self attention relates positions [S1]." }],
  ["citations", { items: [{ marker: 1, page_start: 2, page_end: 2, section: "2.1 Attention", quote: "Self attention relates positions of a sequence." }] }],
  ["done", { message_id: "a1", content: "Self attention relates positions [S1].", status: "complete", retrieval_mode: "hybrid" }],
];

const saved: Message[] = [
  { id: "u1", role: "user", content: "How does attention work?", status: "complete", retrieval_mode: null, citations: [], created_at: "", saved_to_notes: false },
  { id: "a1", role: "assistant", content: "Self attention relates positions [S1].", status: "complete", retrieval_mode: "hybrid",
    citations: [{ marker: 1, page_start: 2, page_end: 2, section: "2.1 Attention", quote: "Self attention relates positions of a sequence." }], created_at: "", saved_to_notes: false },
];

function renderPanel() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ChatPanel paperId="p1" />
    </QueryClientProvider>,
  );
}

let fetchMock: ReturnType<typeof vi.fn<(...args: unknown[]) => Promise<Response>>>;

beforeEach(() => {
  configureAuth(() => Promise.resolve("tok"), () => undefined);
  vi.mocked(getStatus).mockResolvedValue(READY);
  vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
  vi.mocked(createConversation).mockResolvedValue(CONVERSATION);
  vi.mocked(listMessages).mockResolvedValue([]);
  vi.mocked(getSuggestions).mockResolvedValue(["Which datasets are used for training?", "What are the main results?"]);
  fetchMock = vi.fn<(...args: unknown[]) => Promise<Response>>(() => Promise.resolve(sse(ANSWER)));
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => setTimeout(() => { cb(0); }, 0));
  vi.stubGlobal("cancelAnimationFrame", (id: number) => { clearTimeout(id); });
});

describe("AC9, AC10: Ask Abstract panel", () => {
  it("explains and disables input until the paper is indexed", async () => {
    vi.mocked(getStatus).mockResolvedValue(status());
    renderPanel();
    expect(await screen.findByText(/Chat opens as soon as the paper is indexed/)).toBeInTheDocument();
    expect(screen.getByLabelText("Ask about this paper")).toBeDisabled();
  });

  it("offers example questions and starts a conversation for them", async () => {
    vi.mocked(listConversations).mockResolvedValue([]);
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: "What are the main results?" }));
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/conversations/c1/messages");
    expect(JSON.parse(init.body as string)).toEqual({ content: "What are the main results?" });
    expect((init.headers as Record<string, string>)["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("streams an answer with activity, then shows it with expandable citations", async () => {
    let release: () => void = () => undefined;
    fetchMock.mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          release = () => {
            resolve(sse(ANSWER));
          };
        }),
    );
    renderPanel();
    const input = await screen.findByLabelText("Ask about this paper");
    fireEvent.change(input, { target: { value: "How does attention work?" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(await screen.findByText("How does attention work?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
    vi.mocked(listMessages).mockResolvedValue(saved);
    await act(async () => {
      release();
      await new Promise((r) => setTimeout(r, 20));
    });
    const chip = await screen.findByRole("button", { name: "[1] p. 2 (2.1 Attention)" });
    expect(screen.getByText(/Self attention relates positions \[1\]/)).toBeInTheDocument();
    fireEvent.click(chip);
    expect(screen.getByText("Self attention relates positions of a sequence.")).toBeInTheDocument();
  });

  it("keeps the question when the conversation cannot be started", async () => {
    vi.mocked(listConversations).mockResolvedValue([]);
    vi.mocked(createConversation).mockRejectedValue(new Error("Internal error"));
    renderPanel();
    const input = await screen.findByLabelText("Ask about this paper");
    fireEvent.change(input, { target: { value: "What is new here?" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await vi.waitFor(() => { expect(input).toHaveValue("What is new here?"); });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("Shift+Enter adds a new line instead of sending; long text is capped", async () => {
    renderPanel();
    const input = await screen.findByLabelText("Ask about this paper");
    fireEvent.change(input, { target: { value: "line one" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(input).toHaveAttribute("maxLength", "4000"); // AC16
  });

  it("Stop tells the server, then aborts the answer stream", async () => {
    let signal: AbortSignal | undefined;
    const urls: string[] = [];
    fetchMock.mockImplementation((...args: unknown[]) => {
      const target = args[0];
      urls.push(typeof target === "string" ? target : target instanceof Request ? target.url : String(target));
      if (urls[urls.length - 1]?.endsWith("/stop")) return Promise.resolve(new Response(null, { status: 204 }));
      signal ??= (args[1] as RequestInit | undefined)?.signal ?? undefined;
      return Promise.resolve(sse(ANSWER.slice(0, 2), true));
    });
    renderPanel();
    const input = await screen.findByLabelText("Ask about this paper");
    fireEvent.change(input, { target: { value: "Explain it" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(await screen.findByText("Searching the paper")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() => { expect(signal?.aborted).toBe(true); });
    expect(urls.some((u) => u.endsWith("/api/v1/conversations/c1/stop"))).toBe(true);
  });

  it("a failed send offers Retry with the same Idempotency-Key", async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "The model is busy." }), { status: 503 }));
    renderPanel();
    const input = await screen.findByLabelText("Ask about this paper");
    fireEvent.change(input, { target: { value: "Explain it" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(await screen.findByText("The model is busy.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
    const keys = fetchMock.mock.calls.map((call) => ((call[1] as RequestInit).headers as Record<string, string>)["Idempotency-Key"]);
    expect(keys[0]).toBe(keys[1]);
  });

  it("shows suggestions after a refusal", async () => {
    fetchMock.mockResolvedValue(sse([
      ["accepted", { conversation_id: "c1", user_message_id: "u1" }],
      ["delta", { text: "I can only answer questions about this paper." }],
      ["done", { message_id: "a1", content: "I can only answer questions about this paper.", status: "refused", retrieval_mode: null, suggestions: ["Which datasets were used?"] }],
    ]));
    vi.mocked(listMessages).mockResolvedValueOnce([]).mockResolvedValue(saved);
    renderPanel();
    const input = await screen.findByLabelText("Ask about this paper");
    fireEvent.change(input, { target: { value: "What is the weather?" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(await screen.findByRole("button", { name: "Which datasets were used?" })).toBeInTheDocument();
  });

  it("has no serious accessibility violations", async () => {
    vi.mocked(listMessages).mockResolvedValue(saved);
    const { container } = renderPanel();
    await screen.findByRole("button", { name: "[1] p. 2 (2.1 Attention)" });
    expect(await seriousViolations(container)).toEqual([]);
    expect(within(container).getByRole("button", { name: "Send" })).toBeDisabled();
  });
});

describe("Spec 009 AC9: tables and figures in answers", () => {
  it("labels a table citation like the paper does", async () => {
    vi.mocked(getStatus).mockResolvedValue(READY);
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    vi.mocked(listMessages).mockResolvedValue([
      saved[0] as Message,
      {
        ...(saved[1] as Message),
        content: "The big model reaches 28.4 BLEU [S1].",
        citations: [
          {
            marker: 1, page_start: 8, page_end: 8, section: "Table 2", quote: "",
            element: { id: "t2", kind: "table", label: "Table 2", box: { x: 0.1, y: 0.2, width: 0.7, height: 0.2 } },
          },
        ],
      },
    ]);
    renderPanel();
    expect(await screen.findByRole("button", { name: "[1] Table 2, p. 8" })).toBeInTheDocument();
  });
});

describe("Spec 009 AC10: ask about a region", () => {
  it("sends the region drawn in the viewer with the next question, then clears it", async () => {
    function AskButton() {
      const viewer = useCitations();
      return (
        <button type="button" onClick={() => { viewer?.askRegion({ page: 4, x: 0.1, y: 0.2, width: 0.5, height: 0.3 }); }}>
          draw
        </button>
      );
    }
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <CitationProvider>
          <AskButton />
          <ChatPanel paperId="p1" />
        </CitationProvider>
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "draw" }));
    expect(await screen.findByRole("button", { name: "Region, p. 4" })).toBeInTheDocument();
    const input = await screen.findByLabelText("Ask about this paper");
    fireEvent.change(input, { target: { value: "What does this show?" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await vi.waitFor(() => { expect(fetchMock).toHaveBeenCalled(); });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({
      content: "What does this show?",
      region: { page: 4, x: 0.1, y: 0.2, width: 0.5, height: 0.3 },
    });
    expect(screen.queryByRole("button", { name: "Remove Region, p. 4" })).toBeNull(); // cleared
  });
});

describe("AC15 and helpers", () => {
  it("announces completed sentences only", () => {
    expect(completedSentences("First sentence. Second is still stream")).toBe("First sentence.");
    expect(completedSentences("no end yet")).toBe("");
  });

  it("turns passage markers into numbered references", () => {
    expect(withMarkers("A claim [S1][S2]. Another [S3].")).toBe("A claim [1] [2]. Another [3].");
    expect(withMarkers("Grouped claim [S1, S2].")).toBe("Grouped claim [1, 2].");
  });
});

function withViewer(child: ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <CitationProvider>
        {child}
        <ChatPanel paperId="p1" />
      </CitationProvider>
    </QueryClientProvider>,
  );
}

function sentBody(): unknown {
  const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return JSON.parse(init.body as string);
}

describe("Spec 015 AC1: suggested questions", () => {
  it("shows the questions written for this paper in the empty chat", async () => {
    renderPanel();
    expect(await screen.findByRole("button", { name: "Which datasets are used for training?" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "How does the proposed method work?" })).toBeNull();
  });

  it("falls back to the generic questions when they cannot be loaded", async () => {
    vi.mocked(getSuggestions).mockRejectedValue(new Error("down"));
    renderPanel();
    expect(await screen.findByRole("button", { name: "How does the proposed method work?" })).toBeInTheDocument();
  });
});

describe("Spec 015 AC4, AC5: Explain and Ask on selected text", () => {
  function Select({ mode, level = "plain", text = "Multi-head attention attends jointly." }: { mode: "ask" | "explain"; level?: "plain" | "expert"; text?: string }) {
    const viewer = useCitations();
    return (
      <button type="button" onClick={() => { viewer?.askQuote({ page: 3, text, mode, level }); }}>
        select
      </button>
    );
  }

  it("AC4: Explain asks at once at the chosen level with the passage as a quote", async () => {
    withViewer(<Select mode="explain" level="expert" />);
    await screen.findByLabelText("Ask about this paper");
    fireEvent.click(screen.getByRole("button", { name: "select" }));
    await vi.waitFor(() => { expect(fetchMock).toHaveBeenCalled(); });
    expect(sentBody()).toEqual({
      content: "Explain this passage for a researcher in the field.",
      quote: { page: 3, text: "Multi-head attention attends jointly." },
      mode: "explain",
      level: "expert",
    });
  });

  it("AC5: Ask attaches the quote to the next question, then clears it", async () => {
    withViewer(<Select mode="ask" />);
    const input = await screen.findByLabelText("Ask about this paper");
    fireEvent.click(screen.getByRole("button", { name: "select" }));
    expect(await screen.findByRole("button", { name: "Remove quote" })).toBeInTheDocument();
    expect(input).toHaveAttribute("placeholder", "Ask about this passage");
    expect(fetchMock).not.toHaveBeenCalled(); // waits for the user's own question
    fireEvent.change(input, { target: { value: "Why jointly?" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await vi.waitFor(() => { expect(fetchMock).toHaveBeenCalled(); });
    expect(sentBody()).toEqual({ content: "Why jointly?", quote: { page: 3, text: "Multi-head attention attends jointly." }, mode: "ask", level: "plain" });
    expect(screen.queryByRole("button", { name: "Remove quote" })).toBeNull();
  });

  it("AC4: a long selection is trimmed to 1,000 characters with a note", async () => {
    withViewer(<Select mode="ask" text={"word ".repeat(400)} />);
    await screen.findByLabelText("Ask about this paper");
    fireEvent.click(screen.getByRole("button", { name: "select" }));
    expect(await screen.findByText("p. 3, trimmed to 1,000 characters")).toBeInTheDocument();
  });

  it("shows the quote on saved questions", async () => {
    vi.mocked(listMessages).mockResolvedValue([{ ...(saved[0] as Message), quote: { page: 5, text: "Positional encodings use sines." } }, saved[1] as Message]);
    renderPanel();
    expect(await screen.findByText("Positional encodings use sines.")).toBeInTheDocument();
  });
});

describe("Spec 014 AC2: Save to notes", () => {
  it("adds an answer, with its question and sources, to the paper's notes", async () => {
    vi.mocked(listMessages).mockResolvedValue(saved);
    vi.mocked(saveAnswer).mockResolvedValue({ doc: { type: "doc", content: [] }, version: 1, updated_at: "" });
    renderPanel();
    const button = await screen.findByRole("button", { name: "Save to notes" });
    fireEvent.click(button);
    expect(await screen.findByRole("button", { name: "Saved to notes" })).toBeDisabled();
    expect(saveAnswer).toHaveBeenCalledWith("p1", "a1");
  });
});

describe("Production feedback (2026-11-14): sending waits for the conversation; suggestions stay", () => {
  it("does not let a question start a second conversation while the list is loading", async () => {
    let resolveList: (v: (typeof CONVERSATION)[]) => void = () => undefined;
    vi.mocked(listConversations).mockReturnValue(new Promise((r) => { resolveList = r; }));
    renderPanel();
    const input = await screen.findByLabelText("Ask about this paper");
    expect(input).toBeDisabled();
    await act(async () => {
      resolveList([CONVERSATION]);
      await new Promise((r) => setTimeout(r, 0));
    });
    await waitFor(() => { expect(input).toBeEnabled(); });
    expect(createConversation).not.toHaveBeenCalled();
  });

  it("after an answer, offers this paper's questions not asked yet", async () => {
    vi.mocked(listMessages).mockResolvedValue(saved);
    renderPanel();
    const group = await screen.findByRole("group", { name: "Suggested questions" });
    expect(within(group).getByRole("button", { name: "Which datasets are used for training?" })).toBeInTheDocument();
  });
});

describe("Production feedback: Save to notes remembers", () => {
  it("an answer saved before shows Saved to notes after a reload", async () => {
    vi.mocked(listMessages).mockResolvedValue(saved.map((m) => (m.role === "assistant" ? { ...m, saved_to_notes: true } : m)));
    renderPanel();
    expect(await screen.findByRole("button", { name: "Saved to notes" })).toBeDisabled();
  });
});
