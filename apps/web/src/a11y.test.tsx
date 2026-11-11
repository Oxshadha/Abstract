import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { configureDevAuth, resetDevAuthForTests } from "@/auth/devAuth";
import { setAuthState } from "@/auth/state";
import { createAppRouter } from "@/router";
import { seriousViolations } from "@/test/axe";

vi.mock("@/api/me", () => ({
  fetchMe: vi.fn(() =>
    Promise.resolve({
      user: { id: "u1", email: "ada@example.org", display_name: "Ada Lovelace", platform_role: "user" },
      org: { id: "o1", name: "Ada workspace", kind: "personal" },
      role: "owner",
    }),
  ),
}));
vi.mock("@/api/health", () => ({ fetchHealth: vi.fn(() => Promise.resolve("ok")) }));

async function renderAt(path: string) {
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }));
  const { container } = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await router.load();
  return container;
}

describe("AC15: no serious or critical accessibility violations", () => {
  it.each([
    "/",
    "/app/library",
    "/app/home",
    "/app/templates",
    "/app/settings",
    "/app/papers/p1",
    "/missing-page",
  ])("%s", async (path) => {
    setAuthState({ status: "signed-in", provider: "dev" });
    const container = await renderAt(path);
    await screen.findAllByRole("heading");
    expect(await seriousViolations(container)).toEqual([]);
  });

  it("the sign-in dialog over the blurred app", async () => {
    resetDevAuthForTests();
    act(() => {
      configureDevAuth();
    });
    const container = await renderAt("/app/library");
    await screen.findByRole("dialog");
    expect(await seriousViolations(container)).toEqual([]);
  });

  it("the full-page sign-in", async () => {
    resetDevAuthForTests();
    act(() => {
      configureDevAuth();
    });
    const container = await renderAt("/sign-in");
    await screen.findByRole("heading", { name: "Research papers, made clear." });
    expect(await seriousViolations(container)).toEqual([]);
  });
});

describe("AC15: the axe check really catches violations", () => {
  it("reports an image without alt text and an unlabelled button", async () => {
    const { container } = render(
      <main>
        <img src="x.png" />
        <button type="button" />
      </main>,
    );
    const violations = await seriousViolations(container);
    expect(violations.some((v) => v.startsWith("image-alt"))).toBe(true);
    expect(violations.some((v) => v.startsWith("button-name"))).toBe(true);
  });
});
