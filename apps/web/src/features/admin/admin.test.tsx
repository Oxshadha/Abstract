import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchMe } from "@/api/me";
import { setAuthState } from "@/auth/state";
import { Toaster } from "@/components/status/Toaster";
import { getFlags } from "@/features/flags/client";
import { listCollections } from "@/features/library/api";
import { HttpError } from "@/lib/queryClient";
import { createAppRouter } from "@/router";
import { seriousViolations } from "@/test/axe";

import {
  getOverview,
  getOverviewSeries,
  listFlags,
  listJobs,
  listModels,
  listPlans,
  listUsers,
  retryJob,
  setKillSwitch,
  setPlatformCap,
  setUserDisabled,
  setUserPlan,
  updateFlag,
  updateModel,
  updatePlan,
  type ModelEntry,
  type Overview,
  type OverviewSeries,
  type Plan,
} from "./api";
import { shortDate } from "./format";

vi.mock("@/api/me", () => ({ fetchMe: vi.fn() }));
vi.mock("@/features/flags/client", () => ({ getFlags: vi.fn() }));
vi.mock("@/features/library/api", async (orig) => ({ ...(await orig<typeof import("@/features/library/api")>()), listCollections: vi.fn() }));
vi.mock("./api", async (orig) => ({
  ...(await orig<typeof import("./api")>()),
  getOverview: vi.fn(), getOverviewSeries: vi.fn(), setKillSwitch: vi.fn(), setPlatformCap: vi.fn(), listUsers: vi.fn(), setUserPlan: vi.fn(),
  setUserAdmin: vi.fn(), setUserDisabled: vi.fn(), listPlans: vi.fn(), updatePlan: vi.fn(), listFlags: vi.fn(),
  updateFlag: vi.fn(), listJobs: vi.fn(), retryJob: vi.fn(), listModels: vi.fn(), updateModel: vi.fn(),
}));

function me(role: "admin" | "user") {
  return { user: { id: "u1", email: "ada@example.org", display_name: "Ada", platform_role: role }, org: { id: "o1", name: "Ada workspace", kind: "personal" }, role: "owner" };
}

const LIMITS = { papers_per_month: 20, messages_per_day: 100, ai_usd_per_day: 0.5, ai_usd_per_month: 5, fields_per_template: 10, custom_templates: 10, concurrent_jobs: 2, rate_per_minute: { read: 300, write: 60, upload: 20, search: 120 } };
const PLANS: Plan[] = [
  { id: "free", name: "Free", limits: LIMITS, users: 12 },
  { id: "internal", name: "Internal", limits: { ...LIMITS, papers_per_month: null, messages_per_day: null, ai_usd_per_day: null, ai_usd_per_month: null, concurrent_jobs: null, rate_per_minute: null }, users: 3 },
];
const OVERVIEW: Overview = {
  spend_today_usd: 17.2, spend_month_usd: 140, tokens_today: 120000, cap_usd: 20, cap_warning: true, paid_calls_enabled: true,
  by_task: [{ name: "answer", calls: 300, tokens: 90000, cost_usd: 12.5 }], by_model: [{ name: "gemini", calls: 300, tokens: 90000, cost_usd: 12.5 }],
  top_today: [{ user_id: "u2", email: "grace@example.org", display_name: "Grace", spend_usd: 4.2, calls: 80 }], top_month: [],
  queues: { fast: 0, enrichment: 2, scan: 0, deletion: 0 }, provider_errors: [{ provider: "vertex", calls: 100, errors: 3 }],
  jobs: { queued: 1, held: 1, running: 2, failed_24h: 1 },
  papers_in_bin: 3,
};
function seriesFixture(days = 30, empty = false): OverviewSeries {
  return {
    range: days === 7 ? "7d" : days === 90 ? "90d" : "30d",
    days: Array.from({ length: days }, (_, i) => {
      const date = new Date(Date.UTC(2026, 10, 13 - (days - 1 - i))).toISOString().slice(0, 10);
      const last = i === days - 1 && !empty;
      const errors: Record<string, number> = last ? { vertex: 2 } : {};
      return { date, spend_usd: last ? 4.1 : 0, tokens: last ? 900 : 0, papers: last ? 3 : 0, questions: last ? 7 : 0, signups: last ? 2 : 0, active_users: last ? 5 : 0, errors };
    }),
    by_task: empty ? [] : [{ name: "answer", value: 3 }, { name: "summarize", value: 1.1 }],
    by_model: empty ? [] : [{ name: "gemini", value: 4.1 }],
    jobs_by_state: empty ? {} : { succeeded: 40, failed: 2 },
    users_by_plan: empty ? {} : { free: 12, internal: 3 },
  };
}

const MODEL: ModelEntry = {
  task: "embed", routes: [{ provider: "vertex", model: "gemini-embedding-2", input_usd_per_m: 0.1, output_usd_per_m: 0 }],
  params: { max_tokens: 1000 }, deadline_seconds: 10, on_budget: "downgrade", enabled: true, version: 4, updated_at: "2026-11-12T00:00:00Z",
};

async function renderAt(path: string) {
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }));
  const view = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>,
  );
  await router.load();
  return view;
}

beforeEach(() => {
  setAuthState({ status: "signed-in", provider: "dev" });
  vi.mocked(fetchMe).mockResolvedValue(me("admin") as Awaited<ReturnType<typeof fetchMe>>);
  vi.mocked(getFlags).mockResolvedValue({ figures: true, search: true, reading_aids: true });
  vi.mocked(listCollections).mockResolvedValue([]);
  vi.mocked(getOverview).mockResolvedValue(OVERVIEW);
  vi.mocked(getOverviewSeries).mockImplementation((range) => Promise.resolve(seriesFixture(range === "7d" ? 7 : range === "90d" ? 90 : 30)));
  vi.mocked(listPlans).mockResolvedValue(PLANS);
  vi.mocked(listUsers).mockResolvedValue({ items: [{ id: "u2", email: "grace@example.org", display_name: "Grace", plan_id: "free", platform_role: "user", disabled: false, papers: 4, spend_month_usd: 1.25, last_active: "2026-11-12T08:00:00Z", created_at: "2026-11-01T08:00:00Z" }], next_cursor: null });
  vi.mocked(listFlags).mockResolvedValue([{ key: "search", description: "Search across papers", enabled: true, audience: { who: "everyone", plans: [] } }]);
  vi.mocked(listJobs).mockResolvedValue({ items: [{ id: "j1", kind: "ingest", status: "failed", stuck: false, owner_email: "grace@example.org", attempts: 3, last_error: "ParserError: boom", held: false, at: "2026-11-12T08:00:00Z", retryable: true }], counts: { queued: 0, held: 0, running: 0, failed_24h: 1 } });
  vi.mocked(listModels).mockResolvedValue([MODEL]);
  for (const fn of [setKillSwitch, setPlatformCap, setUserPlan, setUserDisabled, updateFlag, retryJob]) vi.mocked(fn).mockResolvedValue();
  vi.mocked(updatePlan).mockResolvedValue(PLANS[0] as Plan);
  vi.mocked(updateModel).mockResolvedValue(MODEL);
});

describe("Spec 011 AC1: who can open Admin", () => {
  it("is hidden from everyone else and their address shows Page not found", async () => {
    vi.mocked(fetchMe).mockResolvedValue(me("user") as Awaited<ReturnType<typeof fetchMe>>);
    await renderAt("/app/admin");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Admin" })).toBeNull();
    expect(getOverview).not.toHaveBeenCalled();
  });

  it("shows Admin in the navigation for admins", async () => {
    await renderAt("/app/home");
    expect((await screen.findAllByRole("link", { name: "Admin" })).length).toBeGreaterThan(0);
  });
});

describe("Spec 011 AC3, AC4, AC13: overview", () => {
  it("shows spend against the cap with the warning, top users and health", async () => {
    const { container } = await renderAt("/app/admin");
    expect(await screen.findByText("Over 80% of the cap")).toBeInTheDocument();
    expect(screen.getByText("$17.20")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Top users today" })).getByText("grace@example.org")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Queues" })).getByText("enrichment")).toBeInTheDocument();
    expect(await seriousViolations(container)).toEqual([]);
  });

  it("saves a new daily cap and pauses AI calls after confirming", async () => {
    await renderAt("/app/admin");
    const cap = await screen.findByLabelText("Daily cap (USD)");
    fireEvent.change(cap, { target: { value: "35" } });
    fireEvent.click(screen.getByRole("button", { name: "Save cap" }));
    await waitFor(() => { expect(setPlatformCap).toHaveBeenCalledWith(35); });
    fireEvent.click(screen.getByRole("switch", { name: "Paid AI calls" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "Pause all paid AI calls?" })).getByRole("button", { name: "Pause" }));
    await waitFor(() => { expect(setKillSwitch).toHaveBeenCalledWith(false); });
  });
});

describe("Spec 011 AC5: users", () => {
  it("changes a user's plan and disables an account", async () => {
    await renderAt("/app/admin/users");
    const list = await screen.findByRole("list", { name: "Users" });
    expect(within(list).getByText(/4 papers/)).toBeInTheDocument();
    fireEvent.click(within(list).getByRole("button", { name: /Plan for Grace/ }));
    fireEvent.click(await screen.findByRole("option", { name: "Internal" }));
    await waitFor(() => { expect(setUserPlan).toHaveBeenCalledWith("u2", "internal"); });
    fireEvent.click(within(list).getByRole("button", { name: "Actions for Grace" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Disable account" }));
    await waitFor(() => { expect(setUserDisabled).toHaveBeenCalledWith("u2", true); });
  });
});

describe("Spec 011 AC12: plans", () => {
  it("saves edited limits; an empty box means no limit", async () => {
    await renderAt("/app/admin/plans");
    const free = (await screen.findAllByLabelText("Papers a month"))[0] as HTMLElement;
    fireEvent.change(free, { target: { value: "25" } });
    const questions = screen.getAllByLabelText("Questions a day")[0] as HTMLElement;
    fireEvent.change(questions, { target: { value: "" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Save" })[0] as HTMLElement);
    await waitFor(() => { expect(updatePlan).toHaveBeenCalled(); });
    expect(vi.mocked(updatePlan).mock.calls[0]).toEqual(["free", { ...LIMITS, papers_per_month: 25, messages_per_day: null }]);
  });
});

describe("Spec 011 AC6, AC8, AC10: flags, jobs, models", () => {
  it("switches a flag off", async () => {
    await renderAt("/app/admin/flags");
    fireEvent.click(await screen.findByRole("switch", { name: "Search" }));
    await waitFor(() => { expect(updateFlag).toHaveBeenCalledWith("search", false, { who: "everyone", plans: [] }); });
  });

  it("retries a failed job", async () => {
    await renderAt("/app/admin/jobs");
    expect(await screen.findByText("ParserError: boom")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry Processing for grace@example.org" }));
    await waitFor(() => { expect(retryJob).toHaveBeenCalledWith("j1"); });
  });

  it("asks to confirm a re-index when the embedding model changes", async () => {
    vi.mocked(updateModel).mockRejectedValueOnce(new HttpError(409, "Changing the embedding model re-indexes every paper."));
    await renderAt("/app/admin/models");
    fireEvent.click(await screen.findByRole("button", { name: "Edit embed" }));
    const dialog = screen.getByRole("dialog", { name: "Model for embed" });
    fireEvent.change(within(dialog).getByLabelText("Primary model"), { target: { value: "new-embedding" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    fireEvent.click(await within(dialog).findByRole("button", { name: "Save and re-index" }));
    await waitFor(() => { expect(updateModel).toHaveBeenCalledTimes(2); });
    expect(vi.mocked(updateModel).mock.calls[1]?.[1]).toBe(4); // If-Match: the version it was loaded at
    expect(vi.mocked(updateModel).mock.calls[1]?.[2].confirm_reindex).toBe(true);
  });
});

describe("Spec 011 AC7: flags gate the UI", () => {
  it("hides search while the search flag is off", async () => {
    vi.mocked(getFlags).mockResolvedValue({ figures: true, search: false, reading_aids: true });
    await renderAt("/app/home");
    await waitFor(() => { expect(getFlags).toHaveBeenCalled(); });
    await waitFor(() => { expect(screen.queryByRole("button", { name: "Search" })).toBeNull(); });
  });
});

describe("Spec 018 AC1 to AC3: the admin sidebar", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("AC1: groups the sections, marks the current page and badges failed jobs", async () => {
    await renderAt("/app/admin/users");
    const sidebar = await screen.findByRole("complementary", { name: "Admin" });
    const monitor = within(sidebar).getByRole("group", { name: "Monitor" });
    const manage = within(sidebar).getByRole("group", { name: "Manage" });
    expect(within(monitor).getByRole("link", { name: "Overview" })).toBeInTheDocument();
    expect(await within(monitor).findByRole("link", { name: "Jobs 1 failed" })).toBeInTheDocument();
    for (const name of ["Users", "Plans", "Models", "Flags"]) expect(within(manage).getByRole("link", { name })).toBeInTheDocument();
    expect(within(manage).getByRole("link", { name: "Users" })).toHaveAttribute("aria-current", "page");
    expect(within(sidebar).getByRole("link", { name: "Back to app" })).toHaveAttribute("href", "/app/home");
    // The app sidebar (Library, Templates) is not shown inside Admin.
    expect(screen.queryByRole("navigation", { name: "Main" })).toBeNull();
  });

  it("AC2: collapses to an icon rail that keeps names, and the device remembers it", async () => {
    const view = await renderAt("/app/admin");
    const sidebar = await screen.findByRole("complementary", { name: "Admin" });
    fireEvent.click(within(sidebar).getByRole("button", { name: "Collapse sidebar" }));
    expect(sidebar).toHaveAttribute("data-collapsed", "true");
    expect(within(sidebar).getByRole("link", { name: "Plans" })).toHaveAttribute("title", "Plans");
    expect(window.localStorage.getItem("abstract.admin.sidebar")).toBe("collapsed");
    view.unmount();
    await renderAt("/app/admin");
    const again = await screen.findByRole("complementary", { name: "Admin" });
    expect(again).toHaveAttribute("data-collapsed", "true");
    fireEvent.click(within(again).getAllByRole("button", { name: "Expand sidebar" })[0] as HTMLElement);
    expect(again).toHaveAttribute("data-collapsed", "false");
  });

  it("AC3: phones keep the section pill row, which hides where the sidebar shows", async () => {
    await renderAt("/app/admin");
    const main = await screen.findByRole("main");
    const pills = within(main).getByRole("navigation", { name: "Admin sections" });
    expect(pills).toHaveClass("md:hidden");
    expect(screen.getByRole("complementary", { name: "Admin" })).toHaveClass("hidden", "md:flex");
  });

  it("is not shown to someone who is not an admin", async () => {
    vi.mocked(fetchMe).mockResolvedValue(me("user") as Awaited<ReturnType<typeof fetchMe>>);
    await renderAt("/app/admin");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "Admin" })).toBeNull();
  });
});

describe("Spec 018 AC4 to AC8, AC11: the Overview charts", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("AC4: four summary cards, with the cap warning and failed jobs opening Jobs", async () => {
    await renderAt("/app/admin");
    const failed = await screen.findByRole("link", { name: /Failed jobs/ });
    expect(failed).toHaveAttribute("href", "/app/admin/jobs");
    expect(screen.getByText("Spend today")).toBeInTheDocument();
    expect(screen.getByText("Over 80% of the cap")).toBeInTheDocument(); // cap_warning in the fixture
    expect(screen.getByText("Spend this month")).toBeInTheDocument();
    expect(screen.getByText("Tokens today")).toBeInTheDocument();
  });

  it("019 AC9: the Overview shows how many papers are in Recently deleted, as a count", async () => {
    await renderAt("/app/admin");
    const tile = (await screen.findByText("Recently deleted")).parentElement as HTMLElement;
    expect(within(tile).getByText("3")).toBeInTheDocument();
  });

  it("AC5: spend per day for 30 days by default, switchable and remembered", async () => {
    await renderAt("/app/admin");
    const chart = await screen.findByRole("group", { name: new RegExp(`^Spend per day, last 30 days, highest \\$4\\.10 on ${shortDate("2026-11-13")}`) });
    expect(chart).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /^Spend per day/ }).querySelectorAll("tbody tr")).toHaveLength(30);
    fireEvent.click(screen.getByRole("radio", { name: "7 days" }));
    expect(await screen.findByRole("group", { name: /^Spend per day, last 7 days/ })).toBeInTheDocument();
    expect(getOverviewSeries).toHaveBeenCalledWith("7d");
    expect(window.localStorage.getItem("abstract.admin.range")).toBe("7d");
  });

  it("AC6: papers and questions, active users, sign-ups and AI errors per day", async () => {
    await renderAt("/app/admin");
    expect(await screen.findByRole("group", { name: /^Papers and questions per day, last 30 days: 3 papers, 7 questions/ })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: /^Active users per day, last 30 days, highest 5/ })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: /^New sign-ups per day, last 30 days, 2 in total/ })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: /^AI errors per day by provider, last 30 days, 2 in total/ })).toBeInTheDocument();
  });

  it("AC7: breakdowns with totals; failed jobs and plans open their pages; task or model", async () => {
    await renderAt("/app/admin");
    expect(await screen.findByRole("figure", { name: /^Spend by task/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Failed\s*\d+%/ })).toHaveAttribute("href", "/app/admin/jobs");
    expect(screen.getByRole("link", { name: /^Free/ })).toHaveAttribute("href", "/app/admin/plans");
    expect(within(screen.getByRole("figure", { name: /^Users by plan/ })).getByText("15")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Model" }));
    expect(screen.getByRole("figure", { name: /^Spend by model/ })).toBeInTheDocument();
  });

  it("AC8: arrow keys read out a day; no serious axe violations", async () => {
    vi.mocked(getOverview).mockResolvedValue({ ...OVERVIEW, cap_usd: 5 }); // $4.10 is over 80%
    const { container } = await renderAt("/app/admin");
    const chart = await screen.findByRole("group", { name: /^Spend per day/ });
    chart.focus();
    fireEvent.keyDown(chart, { key: "End" });
    expect(await screen.findByText(`${shortDate("2026-11-13")}: Spend $4.10. At or over 80% of the cap`)).toBeInTheDocument();
    fireEvent.keyDown(chart, { key: "ArrowLeft" });
    expect(screen.getByText(`${shortDate("2026-11-12")}: Spend $0`)).toBeInTheDocument();
    expect(await seriousViolations(container)).toEqual([]);
  });

  it("AC11: a failed request offers Retry and leaves the page; no data says so", async () => {
    vi.mocked(getOverviewSeries).mockRejectedValueOnce(new Error("Could not load the charts."));
    await renderAt("/app/admin");
    expect(await screen.findByText("Could not load the charts.")).toBeInTheDocument();
    expect(screen.getByText("Spend this month")).toBeInTheDocument(); // the rest still shows
    vi.mocked(getOverviewSeries).mockResolvedValueOnce(seriesFixture(30, true));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect((await screen.findAllByText("No usage yet")).length).toBeGreaterThan(0);
  });
});
