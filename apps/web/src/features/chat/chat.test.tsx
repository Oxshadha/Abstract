import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { configureAuth } from "@/auth/session";
import { getStatus } from "@/features/papers/api";
import { status } from "@/features/papers/fixtures";
import { seriousViolations } from "@/test/axe";

import { createConversation, listConversations, listMessages, type Message } from "./api";
import { ChatPanel } from "./ChatPanel";
import { withMarkers } from "./markers";
import { completedSentences } from "./useChat";

vi.mock("@/features/papers/api", async (orig) => ({ ...(await orig<typeof import("@/features/papers/api")>()), getStatus: vi.fn() }));
vi.mock("./api", async (orig) => ({
  ...(await orig<typeof import("./api")>()),
  listConversations: vi.fn(), createConversation: vi.fn(), listMessages: vi.fn(),
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
  { id: "u1", role: "user", content: "How does attention work?", status: "complete", retrieval_mode: null, citations: [], created_at: "" },
  { id: "a1", role: "assistant", content: "Self attention relates positions [S1].", status: "complete", retrieval_mode: "hybrid",
    citations: [{ marker: 1, page_start: 2, page_end: 2, section: "2.1 Attention", quote: "Self attention relates positions of a sequence." }], created_at: "" },
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

  it("Shift+Enter adds a new line instead of sending; long text is capped", async () => {
    renderPanel();
    const input = await screen.findByLabelText("Ask about this paper");
    fireEvent.change(input, { target: { value: "line one" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(input).toHaveAttribute("maxLength", "4000"); // AC16
  });

  it("Stop aborts the answer stream", async () => {
    let signal: AbortSignal | undefined;
    fetchMock.mockImplementation((...args: unknown[]) => {
      signal = (args[1] as RequestInit).signal ?? undefined;
      return Promise.resolve(sse(ANSWER.slice(0, 2), true));
    });
    renderPanel();
    const input = await screen.findByLabelText("Ask about this paper");
    fireEvent.change(input, { target: { value: "Explain it" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(await screen.findByText("Searching the paper")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(signal?.aborted).toBe(true);
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
