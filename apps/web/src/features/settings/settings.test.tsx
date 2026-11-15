import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { setAuthState } from "@/auth/state";
import { listCollections } from "@/features/library/api";
import { createAppRouter } from "@/router";
import { seriousViolations } from "@/test/axe";

import { deleteAccount, getUsage, type Usage } from "./api";
import { meterValue, resetLabel } from "./format";

vi.mock("@/api/me", () => ({
  fetchMe: vi.fn(() =>
    Promise.resolve({
      user: { id: "u1", email: "ada@example.org", display_name: "Ada Lovelace", platform_role: "user" },
      org: { id: "o1", name: "Ada workspace", kind: "personal" },
      role: "owner",
    }),
  ),
}));
vi.mock("@/features/library/api", async (orig) => ({ ...(await orig<typeof import("@/features/library/api")>()), listCollections: vi.fn() }));
vi.mock("./api", async (orig) => ({ ...(await orig<typeof import("./api")>()), getUsage: vi.fn(), deleteAccount: vi.fn() }));

const FREE: Usage = {
  plan: { id: "free", name: "Free" },
  meters: [
    { key: "papers", used: 3, limit: 20, resets_at: "2026-12-01T00:00:00Z" },
    { key: "messages", used: 12, limit: 100, resets_at: "2026-11-13T00:00:00Z" },
    { key: "ai", used: 40, limit: 100, resets_at: "2026-11-13T00:00:00Z" },
  ],
};
const signOut = vi.fn();

async function renderSettings() {
  const router = createAppRouter(createMemoryHistory({ initialEntries: ["/app/settings"] }));
  const view = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await router.load();
  return view;
}

beforeEach(() => {
  signOut.mockReset();
  setAuthState({ status: "signed-in", provider: "dev", signOut });
  vi.mocked(listCollections).mockResolvedValue([]);
  vi.mocked(getUsage).mockResolvedValue(FREE);
  vi.mocked(deleteAccount).mockResolvedValue();
});

describe("Settings (spec 012 AC11 to AC16)", () => {
  it("AC11, AC12: shows the profile, the plan and a meter per limit", async () => {
    const { container } = await renderSettings();
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("ada@example.org")).toBeInTheDocument();
    expect(screen.getByText(/Your name and email come from your sign-in account/)).toBeInTheDocument();
    const usage = await screen.findByRole("list", { name: "Usage" });
    expect(within(usage).getByText("3 of 20")).toBeInTheDocument();
    expect(within(usage).getByText("40% of today's allowance")).toBeInTheDocument();
    expect(within(usage).getByRole("progressbar", { name: "Papers this month" })).toHaveAttribute("aria-valuenow", "15");
    expect(screen.getByText("Free")).toBeInTheDocument();
    expect(await seriousViolations(container)).toEqual([]);
  });

  it("AC12: a plan without a limit reads No limit, with no bar", async () => {
    vi.mocked(getUsage).mockResolvedValue({
      plan: { id: "internal", name: "Internal" },
      meters: FREE.meters.map((m) => ({ ...m, used: m.key === "ai" ? null : m.used, limit: null })),
    });
    await renderSettings();
    const usage = await screen.findByRole("list", { name: "Usage" });
    expect(within(usage).getAllByText("No limit")).toHaveLength(3);
    expect(within(usage).queryByRole("progressbar")).toBeNull();
  });

  it("AC13, AC14: theme control and sign out", async () => {
    await renderSettings();
    expect(await screen.findByRole("radiogroup", { name: "Theme" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(signOut).toHaveBeenCalled();
  });

  it("AC15: delete asks for the email, then deletes and signs out", async () => {
    await renderSettings();
    fireEvent.click(await screen.findByRole("button", { name: "Delete account" }));
    const dialog = screen.getByRole("dialog", { name: "Delete your account?" });
    const confirm = within(dialog).getByRole("button", { name: "Delete everything" });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Type ada@example.org to confirm"), { target: { value: "ADA@example.org" } });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() => { expect(signOut).toHaveBeenCalled(); });
    expect(deleteAccount).toHaveBeenCalledWith("ADA@example.org");
  });

  it("017 AC17: the delete dialog states the backup horizon", async () => {
    await renderSettings();
    fireEvent.click(await screen.findByRole("button", { name: "Delete account" }));
    const dialog = screen.getByRole("dialog", { name: "Delete your account?" });
    expect(within(dialog).getByText(/gone from the app at once and from backups within 7 days/)).toBeInTheDocument();
  });
});

describe("Spec 012 AC3: limits in the reader's own words", () => {
  it("formats meters and reset times locally", () => {
    expect(meterValue({ key: "messages", used: 2, limit: 100 })).toBe("2 of 100");
    expect(meterValue({ key: "ai", used: null, limit: null })).toBe("No limit");
    expect(resetLabel({ key: "papers", resets_at: "2026-12-01T00:00:00Z" }, "en-GB")).toMatch(/^Resets on 1 Dec/);
    expect(resetLabel({ key: "messages", resets_at: "2026-11-13T00:00:00Z" }, "en-GB")).toMatch(/^Resets at \d/);
  });

});
