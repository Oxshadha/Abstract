import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { seriousViolations } from "@/test/axe";

import { getFileUrl, getPageSizes } from "./api";
import { CitationProvider, useCitations } from "./citations";
import { escapeHtml, locate, markItem, type TextPiece } from "./locate";
import { PdfViewer } from "./PdfViewer";
import { visibleWindow } from "./virtual";

// pdf.js needs a real canvas and worker; the viewer's own logic is what is under test here.
const pageText = new Map<number, TextPiece[]>();
const failRender = { on: false };
const documentProps: { suspense?: boolean }[] = [];
vi.mock("react-pdf", () => ({
  pdfjs: { GlobalWorkerOptions: {} },
  Document: ({ children, suspense }: { children: ReactNode; suspense?: boolean }) => {
    documentProps.push({ suspense });
    return <div data-testid="document">{children}</div>;
  },
  Page: ({ pageNumber, onGetTextSuccess, customTextRenderer, onRenderError }: {
    pageNumber: number;
    onGetTextSuccess?: (c: { items: TextPiece[] }) => void;
    customTextRenderer?: (p: { str: string; itemIndex: number }) => string;
    onRenderError?: (e: Error) => void;
  }) => {
    const items = pageText.get(pageNumber) ?? [];
    useEffect(() => {
      if (failRender.on) onRenderError?.(new Error("boom"));
      else onGetTextSuccess?.({ items }); // once per load, as in react-pdf
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return (
      <div data-testid={`page-${String(pageNumber)}`}>
        {items.map((it, i) => (
          // mirrors react-pdf's text layer, which inserts customTextRenderer's HTML
          <span key={i} dangerouslySetInnerHTML={{ __html: customTextRenderer?.({ str: it.str, itemIndex: i }) ?? it.str }} />
        ))}
      </div>
    );
  },
}));
vi.mock("./api", async (orig) => ({ ...(await orig<typeof import("./api")>()), getFileUrl: vi.fn(), getPageSizes: vi.fn() }));

function Cite({ page, quote }: { page: number; quote: string }) {
  const c = useCitations();
  return <button type="button" onClick={() => { c?.open(page, quote); }}>{`cite ${String(page)}`}</button>;
}

function renderViewer(extra?: ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <CitationProvider>
        {extra}
        <div style={{ height: 800 }}><PdfViewer paperId="p1" /></div>
      </CitationProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  pageText.clear();
  failRender.on = false;
  vi.mocked(getFileUrl).mockResolvedValue("https://files.test/p1.pdf");
  vi.mocked(getPageSizes).mockResolvedValue(Array.from({ length: 12 }, (_, i) => ({ page: i + 1, width: 612, height: 792 })));
});

describe("locate (AC4)", () => {
  it("finds an exact quote across items, ignoring case and whitespace", () => {
    const items = [{ str: "The Transformer uses ", hasEOL: false }, { str: "self   attention.", hasEOL: true }];
    const at = locate(items, "the transformer uses self attention");
    expect(at).toMatchObject({ exact: true, start: { item: 0, offset: 0 }, end: { item: 1 } });
  });

  it("joins words hyphenated at a line end", () => {
    const items = [{ str: "a new architec-", hasEOL: true }, { str: "ture based on attention", hasEOL: false }];
    expect(locate(items, "a new architecture based on attention")?.exact).toBe(true);
  });

  it("falls back to a fuzzy match when the text differs slightly", () => {
    const items = [{ str: "We propose a new simple network architecture, the Transformer, based solely on attention." }];
    const at = locate(items, "We propose a simple new network architecture called the Transformer based solely on attention");
    expect(at?.exact).toBe(false);
  });

  it("returns null when the sentence is not on the page", () => {
    expect(locate([{ str: "Completely unrelated text about cooking pasta." }], "attention is all you need for translation")).toBeNull();
  });

  it("escapes item text and wraps only the located part", () => {
    expect(escapeHtml(`<b>"x" & 'y'</b>`)).toBe("&lt;b&gt;&quot;x&quot; &amp; &#39;y&#39;&lt;/b&gt;");
    const html = markItem("<i>hello world</i>", 0, { start: { item: 0, offset: 3 }, end: { item: 0, offset: 8 }, exact: true });
    expect(html).toBe('&lt;i&gt;<mark class="citation-highlight" data-citation="true">hello</mark> world&lt;/i&gt;');
  });
});

describe("PdfViewer", () => {
  it("AC1: shows the toolbar with page field, paging and zoom", async () => {
    renderViewer();
    expect(await screen.findByText("/ 12")).toBeInTheDocument();
    expect(screen.getByRole("toolbar", { name: "Paper viewer" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
    const zoom = screen.getByRole("button", { name: /^Zoom:\s*Fit width$/ });
    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(zoom).not.toHaveAccessibleName(/^Zoom:\s*Fit width$/);
    // The app's own dropdown, keyboard operable like a native select.
    fireEvent.click(zoom);
    const list = screen.getByRole("listbox", { name: "Zoom" });
    fireEvent.keyDown(list, { key: "Home" });
    fireEvent.keyDown(list, { key: "Enter" });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(zoom).toHaveAccessibleName(/^Zoom:\s*Fit width$/);
    expect(document.querySelector('input[type="number"], select')).toBeNull(); // no native widgets
  });

  it("AC6: renders only the visible pages plus a buffer; the rest are sized placeholders", async () => {
    renderViewer();
    expect(await screen.findByTestId("page-1")).toBeInTheDocument();
    expect(screen.queryByTestId("page-12")).toBeNull();
    const placeholder = document.querySelector('[data-page="12"]') as HTMLElement;
    expect(placeholder.style.height).not.toBe("");
    expect(visibleWindow([0, 100, 200, 300, 400, 500, 600, 700], [90, 90, 90, 90, 90, 90, 90, 90], 300, 150)).toEqual([1, 6]);
  });

  it("AC1 AC8: fits the page to the panel width, remeasured on scroll", async () => {
    renderViewer();
    await screen.findByTestId("page-1");
    const width = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientWidth");
    Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 324 });
    try {
      fireEvent.scroll(screen.getByRole("region", { name: "Paper pages" }));
      // fit width: (324 - 24) / 612 points, so a 612-point page is 300 px wide
      await waitFor(() => { expect((document.querySelector('[data-page="1"]') as HTMLElement).style.width).toBe("300px"); });
    } finally {
      if (width) Object.defineProperty(HTMLElement.prototype, "clientWidth", width);
    }
  });

  it("AC4 AC5: a citation highlights the sentence and announces it", async () => {
    pageText.set(1, [{ str: "Self attention relates positions of a sequence.", hasEOL: true }]);
    renderViewer(<Cite page={1} quote="Self attention relates positions of a sequence." />);
    await screen.findByTestId("page-1"); // page 1 is already on screen before the click
    fireEvent.click(screen.getByRole("button", { name: "cite 1" }));
    await waitFor(() => { expect(document.querySelector("mark.citation-highlight")).not.toBeNull(); });
    expect(screen.getByText("Showing the cited sentence on page 1.")).toBeInTheDocument();
  });

  it("AC4: a sentence that cannot be located shows a calm note", async () => {
    pageText.set(1, [{ str: "Nothing related here at all.", hasEOL: true }]);
    renderViewer(<Cite page={1} quote="Self attention relates positions of a sequence." />);
    await screen.findByTestId("page-1");
    fireEvent.click(screen.getByRole("button", { name: "cite 1" }));
    expect(await screen.findAllByText("Sentence not found on this page; showing page 1.")).not.toHaveLength(0);
    expect(document.querySelector("mark")).toBeNull();
  });

  it("AC5: clicking the page clears the highlight", async () => {
    pageText.set(1, [{ str: "Self attention relates positions of a sequence.", hasEOL: true }]);
    renderViewer(<Cite page={1} quote="Self attention relates positions of a sequence." />);
    await screen.findByTestId("page-1");
    fireEvent.click(screen.getByRole("button", { name: "cite 1" }));
    await waitFor(() => { expect(document.querySelector("mark")).not.toBeNull(); });
    fireEvent.click(screen.getByRole("region", { name: "Paper pages" }));
    await waitFor(() => { expect(document.querySelector("mark")).toBeNull(); });
  });

  it("AC9: a render failure offers Try again and Download PDF", async () => {
    failRender.on = true;
    renderViewer();
    expect(await screen.findByRole("alert")).toHaveTextContent("A page could not be shown.");
    expect(screen.getByRole("link", { name: "Download PDF" })).toHaveAttribute("href", "https://files.test/p1.pdf");
    failRender.on = false;
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Try again" })); await Promise.resolve(); });
    expect(await screen.findByTestId("page-1")).toBeInTheDocument();
  });

  it("never suspends into the app's outer boundary (that reset the chat stream)", async () => {
    renderViewer();
    await screen.findByTestId("page-1");
    expect(documentProps.length).toBeGreaterThan(0);
    expect(documentProps.every((p) => p.suspense === false)).toBe(true);
  });

  it("has no serious accessibility violations", async () => {
    const { container } = renderViewer();
    await screen.findByTestId("page-1");
    expect(await seriousViolations(container)).toEqual([]);
  });
});
