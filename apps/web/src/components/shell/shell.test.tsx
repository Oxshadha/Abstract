import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

  it("mobile drawer opens, closes on Escape and returns focus", async () => {
    await renderAt("/app/library");
    const open = await screen.findByRole("button", { name: "Open navigation" });
    fireEvent.click(open);
    expect(screen.getByRole("dialog", { name: "Navigation" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close navigation" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(open).toHaveFocus();
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
  it("workspace has three panels and a tab bar for phones", async () => {
    await renderAt("/app/papers/paper-123");
    expect(await screen.findByRole("region", { name: "Paper" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Summary" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Chat" })).toBeInTheDocument();
    const chatTab = screen.getByRole("button", { name: "Chat" });
    fireEvent.click(chatTab);
    expect(chatTab).toHaveAttribute("aria-pressed", "true");
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
