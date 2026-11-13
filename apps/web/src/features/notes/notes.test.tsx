import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useCitations } from "@/features/viewer/citation-context";
import { seriousViolations } from "@/test/axe";

import { NotesChangedError, getNotes, saveNotes, type Notes } from "./api";
import { NotesPanel } from "./NotesPanel";

vi.mock("./api", async (orig) => ({ ...(await orig<typeof import("./api")>()), getNotes: vi.fn(), saveNotes: vi.fn() }));
vi.mock("@/features/viewer/citation-context", () => ({ useCitations: vi.fn() }));

const EMPTY: Notes = { doc: { type: "doc", content: [] }, version: 0, updated_at: null };
const SAVED_ANSWER: Notes = {
  version: 3,
  updated_at: "2026-11-13T10:00:00Z",
  doc: {
    type: "doc",
    content: [
      {
        type: "blockquote",
        content: [
          { type: "paragraph", content: [{ type: "text", text: "What BLEU score?", marks: [{ type: "bold" }] }] },
          {
            type: "paragraph",
            content: [
              { type: "text", text: "28.4 BLEU " },
              { type: "text", text: "[1]", marks: [{ type: "source", attrs: { page: 8, quote: "28.4 BLEU on WMT 2014" } }] },
            ],
          },
        ],
      },
    ],
  },
};

/** Type into the editor the way the browser does: change its DOM, which ProseMirror reads back. */
function type(editor: HTMLElement, text: string) {
  const paragraph = editor.querySelector("p");
  if (paragraph) paragraph.textContent = text;
}

function renderNotes() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <NotesPanel paperId="p1" />
    </QueryClientProvider>,
  );
}

const open = vi.fn();

beforeEach(() => {
  vi.mocked(getNotes).mockResolvedValue(EMPTY);
  vi.mocked(saveNotes).mockImplementation((_paper, doc, base) => Promise.resolve({ doc, version: base + 1, updated_at: "" }));
  vi.mocked(useCitations).mockReturnValue({ open } as unknown as ReturnType<typeof useCitations>);
  open.mockClear();
});

describe("spec 014: notes", () => {
  it("AC1: an empty page says what notes are for, with the formatting bar", async () => {
    const { container } = renderNotes();
    const editor = await screen.findByRole("textbox", { name: "Notes" });
    expect(editor.querySelector("[data-placeholder]")?.getAttribute("data-placeholder")).toMatch(/save answers from the chat/);
    for (const name of ["Bold", "Italic", "Heading", "Bulleted list", "Numbered list", "Quote"]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    expect(await seriousViolations(container)).toEqual([]);
  });

  it("AC2: a saved answer shows its question, and its source opens the paper at that page", async () => {
    vi.mocked(getNotes).mockResolvedValue(SAVED_ANSWER);
    renderNotes();
    expect(await screen.findByText("What BLEU score?")).toBeInTheDocument();
    fireEvent.click(screen.getByTitle("Open page 8"));
    expect(open).toHaveBeenCalledWith(8, "28.4 BLEU on WMT 2014");
  });

  it("AC4: saves a second after typing stops, from the version it started at", async () => {
    renderNotes();
    const editor = await screen.findByRole("textbox", { name: "Notes" });
    type(editor, "Key idea");
    await waitFor(() => { expect(saveNotes).toHaveBeenCalledTimes(1); }, { timeout: 3000 });
    const [paper, doc, base] = vi.mocked(saveNotes).mock.calls[0] ?? [];
    expect([paper, base]).toEqual(["p1", 0]);
    expect(JSON.stringify(doc)).toContain("Key idea");
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });

  it("AC4: a change made in another tab offers Reload or Keep mine", async () => {
    vi.mocked(saveNotes).mockRejectedValueOnce(new NotesChangedError("changed"));
    renderNotes();
    const editor = await screen.findByRole("textbox", { name: "Notes" });
    type(editor, "Mine");
    expect(await screen.findByText(/changed in another tab/, {}, { timeout: 3000 })).toBeInTheDocument();
    vi.mocked(getNotes).mockResolvedValue({ ...EMPTY, version: 5 });
    fireEvent.click(screen.getByRole("button", { name: "Keep mine" }));
    await waitFor(() => { expect(saveNotes).toHaveBeenLastCalledWith("p1", expect.anything(), 5); });
  });
});
