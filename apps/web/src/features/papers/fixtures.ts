import type { Paper, PaperStatus } from "./api";

export function paper(overrides: Partial<Paper> = {}): Paper {
  return {
    id: "p1",
    filename: "attention.pdf",
    title: "Attention Is All You Need",
    pages: 15,
    size_bytes: 2_200_000,
    status: "ready",
    text_status: "ready",
    error_message: null,
    created_at: new Date(Date.now() - 2 * 3600_000).toISOString(),
    starred: false,
    last_opened_at: null,
    authors: ["Vaswani", "Shazeer"],
    year: 2017,
    doc_type: "paper",
    ...overrides,
  };
}

export function status(overrides: Partial<PaperStatus> = {}): PaperStatus {
  return {
    paper_id: "p1",
    seq: 3,
    status: "processing",
    text_status: "pending",
    chat_available: false,
    error_message: null,
    waiting: false,
    steps: [
      { key: "uploading", state: "done" },
      { key: "extracting", state: "done" },
      { key: "sections", state: "active" },
      { key: "indexing", state: "pending" },
    ],
    ...overrides,
  };
}
