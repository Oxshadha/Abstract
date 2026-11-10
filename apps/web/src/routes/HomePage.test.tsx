import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { fetchHealth } from "@/api/health";

import { HomePage } from "./HomePage";

vi.mock("@/api/health", () => ({ fetchHealth: vi.fn() }));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <HomePage />
    </QueryClientProvider>,
  );
}

describe("HomePage (spec 001 AC9)", () => {
  it("shows ok when the API is healthy", async () => {
    vi.mocked(fetchHealth).mockResolvedValue("ok");
    renderPage();
    expect(await screen.findByText("ok")).toBeInTheDocument();
  });

  it("shows unreachable when the API is down", async () => {
    vi.mocked(fetchHealth).mockResolvedValue("down");
    renderPage();
    expect(await screen.findByText("unreachable")).toBeInTheDocument();
  });
});
