import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { seriousViolations } from "@/test/axe";

import { getReferences, type References } from "./api";
import { ReferencesPanel } from "./ReferencesPanel";

vi.mock("./api", async (orig) => ({ ...(await orig<typeof import("./api")>()), getReferences: vi.fn() }));

const DONE: References = {
  status: "done",
  items: [
    {
      n: 1,
      label: "1",
      raw: "Ashish Vaswani et al. Attention is all you need. 2017.",
      match: {
        title: "Attention is All you Need",
        authors: ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
        year: 2017,
        venue: "NeurIPS",
        citations: 202800,
        url: "https://www.semanticscholar.org/paper/a1",
        pdf_url: "https://arxiv.org/pdf/1706.03762",
      },
    },
    { n: 2, label: "2", raw: "Some Author. A paper nobody indexed. In Workshop, 2020.", match: null },
  ],
};

function renderRefs() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ReferencesPanel paperId="p1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(getReferences).mockResolvedValue(DONE);
});

describe("spec 014: references", () => {
  it("AC6: a match shows title, authors, year, venue, citations and its links", async () => {
    const { container } = renderRefs();
    const list = await screen.findByRole("list", { name: "References" });
    const rows = within(list).getAllByRole("listitem");
    const matched = rows[0] as HTMLElement;
    const raw = rows[1] as HTMLElement;
    expect(within(matched).getByText("Attention is All you Need")).toBeInTheDocument();
    expect(within(matched).getByText("Ashish Vaswani et al. · 2017 · NeurIPS · 202,800 citations")).toBeInTheDocument();
    expect(within(matched).getByRole("link", { name: /in Semantic Scholar/ })).toHaveAttribute("href", "https://www.semanticscholar.org/paper/a1");
    expect(within(matched).getByRole("link", { name: /Open the PDF/ })).toHaveAttribute("href", "https://arxiv.org/pdf/1706.03762");
    expect(within(raw).getByText(/A paper nobody indexed/)).toBeInTheDocument(); // AC6: no match keeps its text
    expect(within(raw).queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("2 references, 1 found on Semantic Scholar.")).toBeInTheDocument();
    expect(await seriousViolations(container)).toEqual([]);
  });

  it("AC6: while lookups run the list shows at once and says so", async () => {
    vi.mocked(getReferences).mockResolvedValue({ status: "matching", items: DONE.items.map((i) => ({ ...i, match: null })) });
    renderRefs();
    expect(await screen.findByText("2 references. Looking them up on Semantic Scholar.")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("AC5: a paper without a reference list says so", async () => {
    vi.mocked(getReferences).mockResolvedValue({ status: "none", items: [] });
    renderRefs();
    expect(await screen.findByText("No reference list was found in this paper.")).toBeInTheDocument();
  });
});
