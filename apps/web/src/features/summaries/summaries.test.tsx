import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { setAuthState } from "@/auth/state";
import { getPaper } from "@/features/papers/api";
import { paper } from "@/features/papers/fixtures";
import { createAppRouter } from "@/router";
import { seriousViolations } from "@/test/axe";

import { StaleVersionError, createSummary, editField, getSummary, listSummaries, listTemplates, retrySummary } from "./api";
import { DETAILED_ID, QUICK_ID, summary, templates } from "./fixtures";
import { Markdown } from "./Markdown";
import { pageLabel } from "./pages";

vi.mock("@/api/me", () => ({
  fetchMe: vi.fn(() => Promise.resolve({ user: { id: "u1", email: "a@b.c", display_name: "Ada", platform_role: "user" },
    org: { id: "o1", name: "W", kind: "personal" }, role: "owner" })),
}));
vi.mock("@/features/papers/api", async (orig) => ({ ...(await orig<typeof import("@/features/papers/api")>()), getPaper: vi.fn(), listPapers: vi.fn() }));
vi.mock("./api", async (orig) => ({
  ...(await orig<typeof import("./api")>()),
  listTemplates: vi.fn(), listSummaries: vi.fn(), getSummary: vi.fn(), createSummary: vi.fn(),
  editField: vi.fn(), resetField: vi.fn(), retrySummary: vi.fn(),
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

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined))); // event streams stay open
  setAuthState({ status: "signed-in", provider: "dev" });
  vi.mocked(getPaper).mockResolvedValue(paper());
  vi.mocked(listTemplates).mockResolvedValue(templates);
  vi.mocked(listSummaries).mockResolvedValue([{ id: "s1", template_id: QUICK_ID, template_name: "Quick Summary", status: "ready" }]);
  vi.mocked(getSummary).mockResolvedValue(summary());
});

describe("AC2: template step", () => {
  it("preselects Quick Summary and Continue starts it then opens processing", async () => {
    vi.mocked(createSummary).mockResolvedValue({ id: "s1", template_id: QUICK_ID, template_name: "Quick Summary", status: "queued" });
    const { router } = await renderAt("/app/papers/p1/template");
    const quick = await screen.findByRole("radio", { name: /Quick Summary/ });
    expect(quick).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: /Detailed Research Analysis/ })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText("10 sections")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /Detailed Research Analysis/ }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    await vi.waitFor(() => {
      expect(router.state.location.pathname).toBe("/app/papers/p1/processing");
    });
    expect(createSummary).toHaveBeenCalledWith("p1", DETAILED_ID);
  });
});

describe("AC8: summary panel", () => {
  it("shows fields with status labels and expandable sources", async () => {
    await renderAt("/app/papers/p1");
    const panel = await screen.findByRole("region", { name: "Summary" });
    expect(await within(panel).findByText("Research Problem")).toBeInTheDocument();
    expect(within(panel).getByText("Verified")).toBeInTheDocument();
    expect(within(panel).getByText("Provisional")).toBeInTheDocument();
    const chip = within(panel).getByRole("button", { name: "Source: p. 2-3" });
    fireEvent.click(chip);
    expect(within(panel).getByText("invented quote")).toBeInTheDocument();
    expect(within(panel).getByText(/not found word for word/)).toBeInTheDocument();
    expect(screen.getByText("Vaswani et al. · 2017")).toBeInTheDocument();
  });

  it("shows skeletons for fields still being generated", async () => {
    vi.mocked(getSummary).mockResolvedValue(summary({ status: "generating", expected_fields: 5 }));
    await renderAt("/app/papers/p1");
    expect(await screen.findAllByRole("status", { name: "Loading a summary section" })).toHaveLength(3);
    expect(screen.getByText("Building your summary")).toBeInTheDocument();
  });

  it("explains a failure and retries", async () => {
    vi.mocked(getSummary).mockResolvedValue(summary({ status: "failed", fields: [], error_message: "The summary could not be created." }));
    vi.mocked(retrySummary).mockResolvedValue();
    await renderAt("/app/papers/p1");
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    await vi.waitFor(() => {
      expect(retrySummary).toHaveBeenCalledWith("s1");
    });
  });

  it("switching to a template without a summary starts one", async () => {
    vi.mocked(createSummary).mockResolvedValue({ id: "s2", template_id: DETAILED_ID, template_name: "Detailed Research Analysis", status: "queued" });
    await renderAt("/app/papers/p1");
    fireEvent.click(await screen.findByRole("button", { name: /Quick Summary/ }));
    fireEvent.click(screen.getByRole("option", { name: /Detailed Research Analysis/ }));
    await vi.waitFor(() => {
      expect(createSummary).toHaveBeenCalledWith("p1", DETAILED_ID);
    });
  });
});

describe("AC9, AC12: editing", () => {
  it("autosaves 1 s after typing with the summary version, then shows Saved", async () => {
    vi.mocked(editField).mockResolvedValue(4);
    await renderAt("/app/papers/p1");
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText(/Research Problem/), { target: { value: "My words." } });
    expect(editField).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    vi.useRealTimers();
    expect(editField).toHaveBeenCalledWith("s1", "problem_statement", "My words.", 3);
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });

  it("a stale version offers to reload", async () => {
    vi.mocked(editField).mockRejectedValue(new StaleVersionError("stale"));
    await renderAt("/app/papers/p1");
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText(/Research Problem/), { target: { value: "Mine." } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    vi.useRealTimers();
    expect(await screen.findByText(/changed in another tab/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });
});

describe("AC14: safe Markdown", () => {
  it("drops unsafe links and raw HTML, keeps safe links and math", () => {
    const { container } = render(
      <Markdown>{"[bad](javascript:alert(1)) [ok](https://example.org) <img src=x onerror=alert(1)> $E=mc^2$"}</Markdown>,
    );
    const links = container.querySelectorAll("a");
    expect([...links].map((a) => a.getAttribute("href"))).toEqual(["https://example.org"]);
    expect(links[0]).toHaveAttribute("rel", "noopener noreferrer nofollow");
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector(".katex")).not.toBeNull();
  });

  it("formats page ranges without en dashes", () => {
    expect(pageLabel([2, 3, 4, 4])).toBe("p. 2-4");
    expect(pageLabel([7, 1])).toBe("p. 1, 7");
    expect(pageLabel([5])).toBe("p. 5");
  });
});

describe("AC15 (003): new screens are accessible", () => {
  it.each(["/app/papers/p1/template", "/app/papers/p1"])("%s", async (path) => {
    const { container } = await renderAt(path);
    await screen.findAllByRole("heading");
    await screen.findByText(path.endsWith("template") ? "Quick Summary" : "Research Problem");
    expect(await seriousViolations(container)).toEqual([]);
  });
});
