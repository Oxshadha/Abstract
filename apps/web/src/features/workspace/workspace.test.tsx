import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { setAuthState } from "@/auth/state";
import { getFlags } from "@/features/flags/client";
import { getPaper } from "@/features/papers/api";
import { paper } from "@/features/papers/fixtures";
import { getSummary, listSummaries, listTemplates } from "@/features/summaries/api";
import { QUICK_ID, summary, templates } from "@/features/summaries/fixtures";
import { createAppRouter } from "@/router";

import { clampChat, clampSplit, DEFAULT_LAYOUT } from "./layout";

vi.mock("@/api/me", () => ({
  fetchMe: vi.fn(() => Promise.resolve({ user: { id: "u1", email: "a@b.c", display_name: "Ada", platform_role: "user" },
    org: { id: "o1", name: "W", kind: "personal" }, role: "owner" })),
}));
vi.mock("@/features/flags/client", () => ({ getFlags: vi.fn() }));
vi.mock("@/features/papers/api", async (orig) => ({ ...(await orig<typeof import("@/features/papers/api")>()), getPaper: vi.fn() }));
vi.mock("@/features/summaries/api", async (orig) => ({
  ...(await orig<typeof import("@/features/summaries/api")>()), listTemplates: vi.fn(), listSummaries: vi.fn(), getSummary: vi.fn(),
}));

async function renderWorkspace() {
  const router = createAppRouter(createMemoryHistory({ initialEntries: ["/app/papers/p1"] }));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await router.load();
  await screen.findByRole("toolbar", { name: "Panels" });
}

const toggle = (name: string) => screen.getByRole("button", { name });

beforeEach(() => {
  window.localStorage.clear();
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
  setAuthState({ status: "signed-in", provider: "dev" });
  vi.mocked(getPaper).mockResolvedValue(paper());
  vi.mocked(listTemplates).mockResolvedValue(templates);
  vi.mocked(listSummaries).mockResolvedValue([{ id: "s1", template_id: QUICK_ID, template_name: "Quick Summary", status: "ready", template_version: 1 }]);
  vi.mocked(getSummary).mockResolvedValue(summary());
  vi.mocked(getFlags).mockResolvedValue({ figures: true, search: true, reading_aids: true, notes: true, references: true });
});

describe("D79: workspace layout", () => {
  it("opens with Paper and Summary side by side and chat closed", async () => {
    await renderWorkspace();
    expect(screen.getByRole("region", { name: "Paper" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Summary" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Ask Abstract" })).not.toBeInTheDocument();
    expect(screen.getByRole("separator", { name: "Resize Paper and Summary" })).toHaveAttribute("aria-valuenow", "50");
  });

  it("hides and shows panels but always keeps one open", async () => {
    await renderWorkspace();
    fireEvent.click(toggle("Paper"));
    expect(screen.queryByRole("region", { name: "Paper" })).not.toBeInTheDocument();
    expect(screen.queryByRole("separator")).not.toBeInTheDocument();
    expect(toggle("Summary")).toBeDisabled(); // the last open panel cannot be hidden
    fireEvent.click(toggle("Paper"));
    expect(screen.getByRole("region", { name: "Paper" })).toBeInTheDocument();
  });

  it("opens chat only on request and closes it", async () => {
    await renderWorkspace();
    fireEvent.click(toggle("Ask Abstract"));
    expect(screen.getByRole("region", { name: "Ask Abstract" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close chat" }));
    expect(screen.queryByRole("region", { name: "Ask Abstract" })).not.toBeInTheDocument();
  });

  it("resizes with the keyboard and remembers the layout on this device", async () => {
    await renderWorkspace();
    const divider = screen.getByRole("separator");
    fireEvent.keyDown(divider, { key: "ArrowRight" });
    fireEvent.keyDown(divider, { key: "ArrowRight" });
    expect(divider).toHaveAttribute("aria-valuenow", "60");
    fireEvent.click(toggle("Ask Abstract"));
    const saved = JSON.parse(window.localStorage.getItem("abstract.workspace.layout") ?? "{}") as Record<string, unknown>;
    expect(saved).toMatchObject({ split: 60, chat: true, paper: true, summary: true });
  });

  it("keeps the split within bounds", () => {
    expect(clampSplit(5)).toBe(25);
    expect(clampSplit(99)).toBe(75);
    expect(DEFAULT_LAYOUT).toEqual({ paper: true, summary: true, chat: false, split: 50, chatWidth: 384 });
  });

  it("production feedback: the chat panel resizes too, within bounds", () => {
    expect(clampChat(100)).toBe(320);
    expect(clampChat(2000)).toBe(640);
  });
});

describe("spec 014: Workspace, Notes and References", () => {
  it("AC1, AC9: desktop tabs under the title; Notes sit beside the paper", async () => {
    await renderWorkspace();
    const tabs = screen.getByRole("tablist", { name: "Paper views" });
    expect(screen.getByRole("tab", { name: "Workspace" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: "Notes" }));
    expect(await screen.findByRole("region", { name: "Notes" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Paper" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Summary" })).not.toBeInTheDocument();
    expect(screen.queryByRole("toolbar", { name: "Panels" })).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("tab", { name: "Notes" }), { key: "ArrowRight" });
    expect(screen.getByRole("region", { name: "References" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Paper" })).not.toBeInTheDocument();
    expect(tabs).toBeInTheDocument();
  });

  it("AC8: a feature turned off hides its tab", async () => {
    vi.mocked(getFlags).mockResolvedValue({ notes: false, references: false });
    await renderWorkspace();
    await waitFor(() => { expect(screen.queryByRole("tablist")).not.toBeInTheDocument(); });
  });

  it("AC9: phones get Notes and References in the pill, five icons", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined,
    }));
    const router = createAppRouter(createMemoryHistory({ initialEntries: ["/app/papers/p1"] }));
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    await router.load();
    const pill = await screen.findByRole("navigation", { name: "Workspace panels" });
    const names = within(pill).getAllByRole("button").map((b) => b.getAttribute("aria-label"));
    expect(names).toEqual(["Paper", "Summary", "Chat", "Notes", "References"]);
    fireEvent.click(within(pill).getByRole("button", { name: "References" }));
    expect(await screen.findByRole("region", { name: "References" })).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
