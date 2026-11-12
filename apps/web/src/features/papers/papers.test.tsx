import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { setAuthState } from "@/auth/state";
import { createAppRouter } from "@/router";
import { seriousViolations } from "@/test/axe";

import { listCollections, listLibrary } from "@/features/library/api";

import { getPaper, getStatus } from "./api";
import { paper, status } from "./fixtures";
import { uploadPaper } from "./upload";

vi.mock("@/api/me", () => ({
  fetchMe: vi.fn(() =>
    Promise.resolve({
      user: { id: "u1", email: "ada@example.org", display_name: "Ada", platform_role: "user" },
      org: { id: "o1", name: "Ada workspace", kind: "personal" },
      role: "owner",
    }),
  ),
}));
vi.mock("@/features/library/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/features/library/api")>()),
  listLibrary: vi.fn(),
  listCollections: vi.fn(),
}));
vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  getPaper: vi.fn(),
  getStatus: vi.fn(),
}));
vi.mock("./upload", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./upload")>()),
  uploadPaper: vi.fn(),
}));

async function renderAt(path: string) {
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }));
  const view = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await router.load();
  return { router, container: view.container };
}

const streamFetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(
  () => new Promise<Response>(() => undefined),
);

beforeEach(() => {
  vi.stubGlobal("fetch", streamFetch); // the progress stream stays open
  setAuthState({ status: "signed-in", provider: "dev" });
  vi.mocked(listLibrary).mockResolvedValue({ items: [], next_cursor: null });
  vi.mocked(listCollections).mockResolvedValue([]);
});

describe("AC14: Library list", () => {
  it("lists papers with status pills, pages, size and time", async () => {
    vi.mocked(listLibrary).mockResolvedValue({
      items: [
        paper(),
        paper({ id: "p2", title: "LLM Agents", status: "processing", text_status: "pending" }),
        paper({ id: "p3", title: "Broken", status: "failed", error_message: "This PDF is damaged and cannot be read." }),
      ],
      next_cursor: null,
    });
    await renderAt("/app/library");
    const list = await screen.findByRole("list", { name: "Papers" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(rows[0] as HTMLElement).getAllByText("Ready")[0]).toBeInTheDocument();
    expect(within(rows[0] as HTMLElement).getByText("Vaswani, Shazeer · 2017 · 15 pages")).toBeInTheDocument();
    expect(within(rows[0] as HTMLElement).getByText("2h ago")).toBeInTheDocument();
    expect(within(rows[1] as HTMLElement).getAllByText("Processing")[0]).toBeInTheDocument();
    expect(within(rows[2] as HTMLElement).getAllByText("Failed")[0]).toBeInTheDocument();
    expect(within(rows[2] as HTMLElement).getByText(/damaged/)).toBeInTheDocument();
  });

  it("pages with a cursor", async () => {
    vi.mocked(listLibrary)
      .mockResolvedValueOnce({ items: [paper()], next_cursor: "c1" })
      .mockResolvedValueOnce({ items: [paper({ id: "p9", title: "Older paper" })], next_cursor: null });
    await renderAt("/app/library");
    fireEvent.click(await screen.findByRole("button", { name: "Show more" }));
    expect(await screen.findByText("Older paper")).toBeInTheDocument();
    expect(vi.mocked(listLibrary).mock.calls.map((c) => c[1])).toEqual([null, "c1"]);
    expect(screen.queryByRole("button", { name: "Show more" })).not.toBeInTheDocument();
  });

  it("shows skeletons while loading and an empty state", async () => {
    let resolve: (v: { items: never[]; next_cursor: null }) => void = () => undefined;
    vi.mocked(listLibrary).mockReturnValue(new Promise((r) => (resolve = r)));
    await renderAt("/app/library");
    expect(await screen.findByRole("status", { name: "Loading your papers" })).toBeInTheDocument();
    await act(async () => {
      resolve({ items: [], next_cursor: null });
      await Promise.resolve();
    });
    expect(await screen.findByText("No papers yet")).toBeInTheDocument();
  });
});

describe("AC2: drop zone", () => {
  it("rejects a non-PDF before uploading", async () => {
    await renderAt("/app/home");
    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error("no file input");
    fireEvent.change(input, { target: { files: [new File(["x"], "notes.txt", { type: "text/plain" })] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Please choose a PDF file.");
    expect(uploadPaper).not.toHaveBeenCalled();
  });

  it("is keyboard reachable and accepts a dropped PDF, then opens the template step", async () => {
    vi.mocked(getPaper).mockResolvedValue(paper({ status: "processing" }));
    vi.mocked(getStatus).mockResolvedValue(status());
    vi.mocked(uploadPaper).mockImplementation((_file, { onPhase, onProgress }) => {
      onPhase("uploading");
      onProgress(0.4);
      return Promise.resolve({ paper: paper({ status: "processing" }), job: null, duplicate: false });
    });
    const { router } = await renderAt("/app/home");
    const choose = await screen.findByRole("button", { name: "Choose PDF" });
    choose.focus();
    expect(choose).toHaveFocus();
    const zone = choose.closest("div") as HTMLElement;
    fireEvent.drop(zone, { dataTransfer: { files: [new File(["%PDF-"], "a.pdf", { type: "application/pdf" })] } });
    await vi.waitFor(() => {
      expect(router.state.location.pathname).toBe("/app/papers/p1/template"); // 006 AC2
    });
  });

  it("shows progress and a cancel button while uploading", async () => {
    let signal: AbortSignal | undefined;
    vi.mocked(uploadPaper).mockImplementation((_file, callbacks) => {
      signal = callbacks.signal;
      callbacks.onPhase("uploading");
      callbacks.onProgress(0.42);
      return new Promise(() => undefined);
    });
    await renderAt("/app/home");
    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error("no file input");
    fireEvent.change(input, { target: { files: [new File(["%PDF-"], "a.pdf", { type: "application/pdf" })] } });
    const bar = await screen.findByRole("progressbar", { name: "Upload progress" });
    expect(bar).toHaveAttribute("aria-valuenow", "42");
    fireEvent.click(screen.getByRole("button", { name: "Cancel upload" }));
    expect(signal?.aborted).toBe(true);
  });
});

describe("Spec 012 AC9: a paper waiting for a free slot", () => {
  it("says it waits for the user's other papers and starts on its own", async () => {
    vi.mocked(getPaper).mockResolvedValue(paper({ status: "processing" }));
    vi.mocked(getStatus).mockResolvedValue(status({ waiting: true }));
    await renderAt("/app/papers/p1/processing");
    expect((await screen.findAllByText("Waiting for your other papers to finish. It starts automatically.")).length).toBeGreaterThan(0);
  });
});

describe("AC12: processing page", () => {
  it("shows the mockup steps and enables the workspace once chat is available", async () => {
    vi.mocked(getPaper).mockResolvedValue(paper({ status: "processing" }));
    vi.mocked(getStatus).mockResolvedValue(status());
    await renderAt("/app/papers/p1/processing");
    expect(await screen.findByText("Identifying sections")).toBeInTheDocument();
    expect(screen.getByText("Extracting text")).toBeInTheDocument();
    expect(screen.getByText("Indexing for chat")).toBeInTheDocument();
    expect(screen.getByText("In progress")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Open workspace" })).not.toBeInTheDocument();
    await vi.waitFor(() => {
      expect(streamFetch.mock.calls.some(([url]) => url.endsWith("/api/v1/papers/p1/events"))).toBe(true);
    });
  });

  it("links to the workspace when chat is available", async () => {
    vi.mocked(getPaper).mockResolvedValue(paper());
    vi.mocked(getStatus).mockResolvedValue(
      status({ status: "ready", text_status: "ready", chat_available: true,
        steps: status().steps.map((s) => ({ ...s, state: "done" as const })) }),
    );
    await renderAt("/app/papers/p1/processing");
    expect(await screen.findByRole("link", { name: "Open workspace" })).toHaveAttribute("href", "/app/papers/p1");
    expect(screen.getByText("Your paper is ready.", { selector: "h2" })).toBeInTheDocument();
  });

  it("explains a failure calmly", async () => {
    vi.mocked(getPaper).mockResolvedValue(paper({ status: "failed" }));
    vi.mocked(getStatus).mockResolvedValue(
      status({ status: "failed", error_message: "This PDF is password-protected. Please upload a copy without a password." }),
    );
    await renderAt("/app/papers/p1/processing");
    expect(await screen.findByText(/password-protected/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("We could not process this paper");
  });
});

describe("AC15 (003): new screens have no serious accessibility violations", () => {
  it.each(["/app/library", "/app/papers/p1/processing"])("%s", async (path) => {
    vi.mocked(listLibrary).mockResolvedValue({ items: [paper(), paper({ id: "p2", status: "processing" })], next_cursor: null });
    vi.mocked(getPaper).mockResolvedValue(paper({ status: "processing" }));
    vi.mocked(getStatus).mockResolvedValue(status());
    const { container } = await renderAt(path);
    await screen.findAllByRole("heading");
    await screen.findByText(path.endsWith("processing") ? "Identifying sections" : "Attention Is All You Need",
      {}, { timeout: 2000 }).catch(() => undefined);
    expect(await seriousViolations(container)).toEqual([]);
  });
});
