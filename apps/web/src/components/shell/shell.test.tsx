import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { setAuthState } from "@/auth/state";
import { createAppRouter } from "@/router";

vi.mock("@/api/me", () => ({
  fetchMe: vi.fn(() =>
    Promise.resolve({
      user: { id: "u1", email: "ada@example.org", display_name: "Ada Lovelace", platform_role: "user" },
      org: { id: "o1", name: "Ada Lovelace workspace", kind: "personal" },
      role: "owner",
    }),
  ),
}));

async function renderAt(path: string) {
  setAuthState({ status: "signed-in", provider: "dev" });
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await router.load();
  return router;
}

describe("AC6: app shell", () => {
  it("shows the sidebar, search and the active page", async () => {
    await renderAt("/app/library");
    expect(await screen.findByRole("heading", { name: "Your Library" })).toBeInTheDocument();
    const nav = screen.getAllByRole("navigation", { name: "Main" })[0];
    expect(nav).toBeDefined();
    const libraryLinks = screen.getAllByRole("link", { name: "Library" });
    expect(libraryLinks.some((l) => l.getAttribute("aria-current") === "page")).toBe(true);
    expect(screen.getByRole("button", { name: /search papers/i })).toBeInTheDocument();
  });

  it("phones get the brand in the top bar and a floating pill for navigation (D86)", async () => {
    await renderAt("/app/library");
    expect(await screen.findByRole("link", { name: "abstract. home" })).toHaveAttribute("href", "/app/home");
    const pill = screen.getByRole("navigation", { name: "Navigation" });
    const links = within(pill).getAllByRole("link");
    expect(links.map((l) => l.getAttribute("aria-label"))).toEqual(["Home", "Library", "Templates", "Settings"]);
    expect(within(pill).getByRole("link", { name: "Library" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("button", { name: "Open navigation" })).toBeNull(); // no drawer any more
  });

  it("user menu shows initials, theme choice and sign out", async () => {
    await renderAt("/app/library");
    const avatar = await screen.findByRole("button", { name: /account menu for ada lovelace/i });
    expect(avatar).toHaveTextContent("AL");
    fireEvent.click(avatar);
    expect(screen.getByRole("radiogroup", { name: "Theme" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Sign out" })).toBeInTheDocument();
  });
});

describe("AC7: routes", () => {
  it("workspace on phones shows one panel at a time with a tab bar (D60, D79)", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined,
    }));
    await renderAt("/app/papers/paper-123");
    expect(await screen.findByRole("region", { name: "Summary" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Paper" })).not.toBeInTheDocument();
    const chatTab = screen.getByRole("button", { name: "Chat" });
    fireEvent.click(chatTab);
    expect(chatTab).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("region", { name: "Ask Abstract" })).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it.each(["/app/collections", "/app/templates", "/app/settings"])("%s renders", async (path) => {
    await renderAt(path);
    expect(await screen.findByRole("heading", { level: 1 })).toBeInTheDocument();
  });

  it("unknown routes show a friendly not-found page", async () => {
    await renderAt("/nope/never");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});
