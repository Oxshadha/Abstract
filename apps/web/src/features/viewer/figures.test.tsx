import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { seriousViolations } from "@/test/axe";

import { describeFigure, getElements, getFigureImage, retryEnrichment, type Elements } from "./api";
import { FiguresPanel } from "./FiguresPanel";

vi.mock("./api", async (orig) => ({
  ...(await orig<typeof import("./api")>()),
  getElements: vi.fn(),
  getFigureImage: vi.fn(),
  describeFigure: vi.fn(),
  retryEnrichment: vi.fn(),
}));

const DONE: Elements = {
  status: "done",
  pages_total: 2,
  pages_done: 2,
  pages_parsed_limit: 60,
  tables: [
    {
      id: "t1",
      label: "Table 2",
      page: 8,
      box: { x: 0.1, y: 0.2, width: 0.7, height: 0.2 },
      caption: "Table 2: BLEU scores.",
      cells: [["Model", "BLEU"], ["Big", "28.4"]],
      header_rows: 1,
    },
  ],
  figures: [
    {
      id: "f1",
      label: "Figure 1",
      page: 3,
      box: { x: 0.3, y: 0.1, width: 0.4, height: 0.4 },
      caption: "Figure 1: The Transformer.",
      description: null,
      has_image: true,
    },
  ],
};

function renderPanel(onShow = vi.fn()) {
  const view = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <FiguresPanel paperId="p1" onShow={onShow} />
    </QueryClientProvider>,
  );
  return { onShow, container: view.container };
}

beforeEach(() => {
  vi.mocked(getElements).mockResolvedValue(DONE);
  vi.mocked(getFigureImage).mockResolvedValue("https://s3.test/figures/1.png");
});

describe("Figures & tables (spec 009)", () => {
  it("AC2: shows page progress while the background parse runs", async () => {
    vi.mocked(getElements).mockResolvedValue({ ...DONE, status: "running", pages_total: 11, pages_done: 3, tables: [], figures: [] });
    renderPanel();
    expect(await screen.findByText("Finding tables and figures (page 4 of 11)")).toBeInTheDocument();
  });

  it("AC5: lists tables and figures in page order, tables as accessible HTML tables", async () => {
    renderPanel();
    const list = await screen.findByRole("list", { name: "Tables and figures" });
    const items = within(list).getAllByRole("listitem");
    expect(items.map((i) => within(i).getByText(/, p\. \d+$/).textContent)).toEqual(["Figure 1, p. 3", "Table 2, p. 8"]);
    const table = within(items[1] as HTMLElement).getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Model", "BLEU"]);
    expect(await within(items[0] as HTMLElement).findByRole("img", { name: "Figure 1: The Transformer." })).toHaveAttribute("src", "https://s3.test/figures/1.png");
    expect(screen.getByText("1 table and 1 figure")).toBeInTheDocument();
  });

  it("AC6: Show in paper passes the page, box and label to the viewer", async () => {
    const { onShow } = renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: "Show Table 2 in the paper" }));
    expect(onShow).toHaveBeenCalledWith(8, DONE.tables[0]?.box, "Table 2");
  });

  it("AC7: describes a figure on request, labelled as AI-generated", async () => {
    vi.mocked(describeFigure).mockResolvedValue("A diagram of an encoder and a decoder stack.");
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: "Describe this figure" }));
    expect(await screen.findByText("A diagram of an encoder and a decoder stack.")).toBeInTheDocument();
    expect(screen.getByText("AI-generated description")).toBeInTheDocument();
  });

  it("AC2: a failed parse keeps the paper usable and offers Retry", async () => {
    vi.mocked(getElements).mockResolvedValue({ ...DONE, status: "failed", tables: [], figures: [] });
    vi.mocked(retryEnrichment).mockResolvedValue();
    renderPanel();
    expect(await screen.findByRole("alert")).toHaveTextContent("still work");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => { expect(retryEnrichment).toHaveBeenCalledWith("p1"); });
  });

  it("explains a paper without tables or figures", async () => {
    vi.mocked(getElements).mockResolvedValue({ ...DONE, tables: [], figures: [] });
    renderPanel();
    expect(await screen.findByText("This paper has no tables or figures.")).toBeInTheDocument();
  });

  it("has no serious accessibility violations", async () => {
    const { container } = renderPanel();
    await screen.findByRole("table");
    expect(await seriousViolations(container)).toEqual([]);
  });
});
