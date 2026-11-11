import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { setAuthState } from "@/auth/state";
import { getPaper } from "@/features/papers/api";
import { paper } from "@/features/papers/fixtures";
import { getSummary, listSummaries, listTemplates } from "@/features/summaries/api";
import { QUICK_ID, summary, templates } from "@/features/summaries/fixtures";
import { createAppRouter } from "@/router";

import { clampSplit, DEFAULT_LAYOUT } from "./layout";

vi.mock("@/api/me", () => ({
  fetchMe: vi.fn(() => Promise.resolve({ user: { id: "u1", email: "a@b.c", display_name: "Ada", platform_role: "user" },
    org: { id: "o1", name: "W", kind: "personal" }, role: "owner" })),
}));
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
  vi.mocked(listSummaries).mockResolvedValue([{ id: "s1", template_id: QUICK_ID, template_name: "Quick Summary", status: "ready" }]);
  vi.mocked(getSummary).mockResolvedValue(summary());
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
    expect(DEFAULT_LAYOUT).toEqual({ paper: true, summary: true, chat: false, split: 50 });
  });
});
