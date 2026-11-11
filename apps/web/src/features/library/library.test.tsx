import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setAuthState } from "@/auth/state";
import { Toaster } from "@/components/status/Toaster";
import { paper } from "@/features/papers/fixtures";
import { createAppRouter } from "@/router";
import { seriousViolations } from "@/test/axe";

import { listCollections, listLibrary, searchPapers, setMembership, updatePaper } from "./api";
import { DEBOUNCE_MS } from "./search-text";

vi.mock("@/api/me", () => ({
  fetchMe: vi.fn(() =>
    Promise.resolve({
      user: { id: "u1", email: "ada@example.org", display_name: "Ada", platform_role: "user" },
      org: { id: "o1", name: "Ada workspace", kind: "personal" },
      role: "owner",
    }),
  ),
}));
vi.mock("./api", async (orig) => ({
  ...(await orig<typeof import("./api")>()),
  listLibrary: vi.fn(),
  listCollections: vi.fn(),
  searchPapers: vi.fn(),
  updatePaper: vi.fn(),
  setMembership: vi.fn(),
}));

const RAG = "11111111-1111-4111-8111-111111111111";

async function renderAt(path: string) {
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }));
  const view = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>,
  );
  await router.load();
  return { router, container: view.container };
}

beforeEach(() => {
  setAuthState({ status: "signed-in", provider: "dev" });
  vi.mocked(listLibrary).mockResolvedValue({ items: [paper(), paper({ id: "p2", title: "LLM Agents", authors: ["Wang", "Li", "Chen"], year: 2024 })], next_cursor: null });
  vi.mocked(listCollections).mockResolvedValue([{ id: RAG, name: "RAG & LLMs", paper_count: 16 }]);
  vi.mocked(searchPapers).mockResolvedValue({ papers: [], passages: [] });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Home (D83)", () => {
  it("shows the upload area and the five most recently opened papers", async () => {
    await renderAt("/app/home");
    expect(await screen.findByRole("heading", { name: "Upload a research paper" })).toBeInTheDocument();
    const recent = await screen.findByRole("list", { name: "Recently opened papers" });
    expect(within(recent).getAllByRole("listitem")).toHaveLength(2);
    expect(vi.mocked(listLibrary).mock.calls[0]?.[0]).toEqual({ sort: "opened" });
    expect(vi.mocked(listLibrary).mock.calls[0]?.[3]).toBe(5);
    expect(screen.getByRole("link", { name: /View all in Library/ })).toHaveAttribute("href", "/app/library");
  });

  it("/app lands on Home", async () => {
    const { router } = await renderAt("/app");
    await waitFor(() => { expect(router.state.location.pathname).toBe("/app/home"); });
  });
});

describe("Library (AC1 to AC4)", () => {
  it("AC1 AC2: Add Paper, rows with authors and year, and a menu per paper", async () => {
    await renderAt("/app/library");
    expect(await screen.findByRole("button", { name: "Add Paper" })).toBeInTheDocument();
    const rows = within(await screen.findByRole("list", { name: "Papers" })).getAllByRole("listitem");
    expect(within(rows[1] as HTMLElement).getByText("Wang et al. · 2024 · 15 pages")).toBeInTheDocument();
    fireEvent.click(within(rows[0] as HTMLElement).getByRole("button", { name: /Actions for Attention/ }));
    expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Star", "Add to collection", "Rename", "Delete"]);
  });

  it("AC3: filters and sort live in the URL", async () => {
    const { router } = await renderAt("/app/library?starred=true&sort=title");
    await screen.findByRole("list", { name: "Papers" });
    expect(vi.mocked(listLibrary).mock.calls.at(-1)?.[0]).toEqual({ sort: "title", starred: true });
    expect(screen.getByRole("button", { name: "Starred" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    await waitFor(() => { expect(router.state.location.search).toEqual({ sort: "title" }); });
  });

  it("AC4: grid and list views", async () => {
    await renderAt("/app/library");
    await screen.findByRole("list", { name: "Papers" });
    fireEvent.click(screen.getByRole("button", { name: "Grid view" }));
    expect(screen.getByRole("button", { name: "Grid view" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("list", { name: "Papers" }).className).toContain("grid");
  });

  it("has no serious accessibility violations", async () => {
    const { container } = await renderAt("/app/library");
    await screen.findByRole("list", { name: "Papers" });
    expect(await seriousViolations(container)).toEqual([]);
  });
});

describe("Star (AC5, AC12)", () => {
  it("stars at once and rolls back with a toast when the server refuses", async () => {
    let refuse: (err: Error) => void = () => undefined;
    vi.mocked(updatePaper).mockReturnValue(new Promise((_resolve, reject) => { refuse = reject; }));
    await renderAt("/app/library");
    const star = (await screen.findAllByRole("button", { name: /^Star Attention/ }))[0] as HTMLElement;
    fireEvent.click(star);
    expect(await screen.findByRole("button", { name: /^Unstar Attention/ })).toBeInTheDocument(); // optimistic
    act(() => { refuse(new Error("Could not update the paper.")); });
    expect(await screen.findByText("Could not update the paper.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /^Star Attention/ })).toHaveAttribute("aria-pressed", "false");
  });
});

describe("Collections in the sidebar (AC6, AC7)", () => {
  it("lists collections with counts and opens the Library filtered to one", async () => {
    await renderAt("/app/library");
    const link = await screen.findByRole("link", { name: /RAG & LLMs/ });
    expect(link).toHaveAttribute("href", `/app/library?collection=${RAG}`);
    expect(within(link).getByText("16")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Collections" })).toBeNull(); // folders, not a page (D82)
  });

  it("collection menus float above the sidebar, with Delete in red", async () => {
    await renderAt("/app/library");
    fireEvent.click(await screen.findByRole("button", { name: "Actions for collection RAG & LLMs" }));
    const menu = screen.getByRole("menu");
    expect(menu.parentElement).toBe(document.body); // portal: never clipped by the sidebar's scroll
    expect(within(menu).getByRole("menuitem", { name: "Delete" })).toHaveClass("text-error");
    expect(within(menu).getByRole("menuitem", { name: "Rename" })).not.toHaveClass("text-error");
  });

  it("inside a collection a paper can be moved to another collection or removed", async () => {
    const OTHER = "22222222-2222-4222-8222-222222222222";
    vi.mocked(listCollections).mockResolvedValue([
      { id: RAG, name: "RAG & LLMs", paper_count: 2 },
      { id: OTHER, name: "Healthcare AI", paper_count: 9 },
    ]);
    vi.mocked(setMembership).mockResolvedValue();
    await renderAt(`/app/library?collection=${RAG}`);
    const rows = within(await screen.findByRole("list", { name: "Papers" })).getAllByRole("listitem");
    fireEvent.click(within(rows[0] as HTMLElement).getByRole("button", { name: /Actions for Attention/ }));
    expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual([
      "Star", "Add to collection", "Move to collection", "Remove from this collection", "Rename", "Delete",
    ]);
    fireEvent.click(screen.getByRole("menuitem", { name: "Move to collection" }));
    fireEvent.click(within(await screen.findByRole("list", { name: "Move to" })).getByRole("button", { name: /Healthcare AI/ }));
    await waitFor(() => {
      expect(vi.mocked(setMembership).mock.calls).toEqual([[OTHER, "p1", true], [RAG, "p1", false]]); // add, then remove
    });
  });

  it("a collection view shows its name and asks only for its papers", async () => {
    await renderAt(`/app/library?collection=${RAG}`);
    expect(await screen.findByRole("heading", { level: 1, name: "RAG & LLMs" })).toBeInTheDocument();
    expect(vi.mocked(listLibrary).mock.calls.at(-1)?.[0]).toEqual({ sort: "added", collection: RAG });
  });
});

describe("Search (AC8, AC10)", () => {
  it("opens with Ctrl+K, waits for typing to pause, and skips one-character queries", async () => {
    await renderAt("/app/library");
    await screen.findByRole("list", { name: "Papers" });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    const box = await screen.findByRole("combobox", { name: "Search papers" });
    fireEvent.change(box, { target: { value: "a" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(DEBOUNCE_MS + 50); });
    expect(searchPapers).not.toHaveBeenCalled();
    vi.mocked(searchPapers).mockResolvedValue({
      papers: [{ id: "p1", title: "Attention Is All You Need", authors: ["Vaswani"], year: 2017 }],
      passages: [{ paper_id: "p1", paper_title: "Attention Is All You Need", page: 3, snippet: "self «attention» relates positions" }],
    });
    for (const value of ["at", "att", "atte", "atten"]) fireEvent.change(box, { target: { value } });
    await act(async () => { await vi.advanceTimersByTimeAsync(DEBOUNCE_MS + 50); });
    expect(vi.mocked(searchPapers).mock.calls.map((c) => c[0])).toEqual(["atten"]); // one request, after the pause
    expect(await screen.findByRole("option", { name: /Attention Is All You Need.*Vaswani/ })).toBeInTheDocument();
    const passage = screen.getByRole("option", { name: /p\. 3/ });
    expect(within(passage).getByText("attention").tagName).toBe("MARK");
  });

  it("phones get a search icon instead of a squeezed field", async () => {
    await renderAt("/app/library");
    expect(await screen.findByRole("button", { name: "Search" })).toHaveClass("sm:hidden");
    expect(screen.queryByText("⌘K")).toBeNull(); // no OS-specific badge (D82)
  });
});
