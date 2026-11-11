import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createAppRouter } from "@/router";

import { configureDevAuth, resetDevAuthForTests } from "./devAuth";

vi.mock("@/api/me", () => ({
  fetchMe: vi.fn(() =>
    Promise.resolve({
      user: { id: "u1", email: "demo@abstract.local", display_name: "Demo Researcher", platform_role: "user" },
      org: { id: "o1", name: "Demo Researcher workspace", kind: "personal" },
      role: "owner",
    }),
  ),
}));

async function renderAt(path: string) {
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await router.load();
}

beforeEach(() => {
  resetDevAuthForTests();
  act(() => {
    configureDevAuth();
  });
});

describe("AC8: sign-in modal over the blurred app (D45, D70)", () => {
  it("signed-out users see a dialog and cannot reach the app underneath", async () => {
    await renderAt("/app/library");
    const dialog = await screen.findByRole("dialog", { name: "Welcome back" });
    expect(dialog).toBeInTheDocument();
    const shell = screen.getByText("Your Library").closest("[inert]");
    expect(shell).not.toBeNull();
  });

  it("continue as demo user unlocks the app, and sign out brings the dialog back", async () => {
    await renderAt("/app/library");
    fireEvent.click(await screen.findByRole("button", { name: "Continue as demo user" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(screen.getByText("Your Library").closest("[inert]")).toBeNull();
    fireEvent.click(await screen.findByRole("button", { name: /account menu/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));
    expect(await screen.findByRole("dialog", { name: "Welcome back" })).toBeInTheDocument();
  });

  it("full-page sign-in uses the split-screen layout", async () => {
    await renderAt("/sign-in");
    expect(await screen.findByRole("heading", { name: "Research papers, made clear." })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue as demo user" })).toBeInTheDocument();
  });
});
