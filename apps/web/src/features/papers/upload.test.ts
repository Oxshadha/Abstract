import { beforeEach, describe, expect, it, vi } from "vitest";

import { createUpload, finalizeUpload, type Paper } from "./api";
import { postToStorage, sha256Hex, UploadCancelledError, uploadPaper, UPLOAD_MAX_BYTES, validatePdf } from "./upload";

function pdf(size = 10, name = "paper.pdf", type = "application/pdf"): File {
  return new File([new Uint8Array(size)], name, { type });
}

class FakeXhr {
  static last: FakeXhr | null = null;
  upload: { onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = {
    onprogress: null,
  };
  status = 0;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  url = "";
  body: FormData | null = null;
  constructor() {
    FakeXhr.last = this;
  }
  open(_method: string, url: string) {
    this.url = url;
  }
  send(body: FormData) {
    this.body = body;
  }
  abort() {
    this.onabort?.();
  }
  finish(status: number) {
    this.status = status;
    this.onload?.();
  }
}

vi.mock("./api", () => ({ createUpload: vi.fn(), finalizeUpload: vi.fn() }));

function lastXhr(): FakeXhr {
  if (!FakeXhr.last) throw new Error("no request was sent");
  return FakeXhr.last;
}

beforeEach(() => {
  FakeXhr.last = null;
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
});

describe("AC2: checks before uploading", () => {
  it("rejects non-PDF, empty and oversize files", () => {
    expect(validatePdf(pdf(10, "notes.docx", "application/msword"))).toMatch(/PDF/);
    expect(validatePdf(pdf(0))).toMatch(/empty/);
    expect(validatePdf(new File(["x"], "big.pdf", { type: "application/pdf" }))).toBeNull();
    const big = pdf(1);
    Object.defineProperty(big, "size", { value: UPLOAD_MAX_BYTES + 1 });
    expect(validatePdf(big)).toMatch(/50 MB/);
  });

  it("accepts a .pdf name even when the browser reports no type", () => {
    expect(validatePdf(pdf(10, "Paper.PDF", ""))).toBeNull();
  });

  it("hashes with SHA-256", async () => {
    expect(await sha256Hex(new Blob(["abc"]))).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
  });
});

describe("AC2: direct upload with progress and cancel", () => {
  it("posts the form fields first and the file last, and reports progress", async () => {
    const progress: number[] = [];
    const done = postToStorage({ url: "https://s3.test/b", fields: { key: "k", policy: "p" } }, pdf(), (f) => progress.push(f), new AbortController().signal);
    const xhr = lastXhr();
    xhr.upload.onprogress?.({ lengthComputable: true, loaded: 5, total: 10 });
    xhr.finish(204);
    await done;
    expect(progress).toEqual([0.5]);
    expect(xhr.url).toBe("https://s3.test/b");
    expect([...(xhr.body?.keys() ?? [])]).toEqual(["key", "policy", "file"]);
  });

  it("cancel aborts the transfer", async () => {
    const controller = new AbortController();
    const done = postToStorage({ url: "u", fields: {} }, pdf(), () => undefined, controller.signal);
    controller.abort();
    await expect(done).rejects.toBeInstanceOf(UploadCancelledError);
  });

  it("a rejected upload is a clear error", async () => {
    const done = postToStorage({ url: "u", fields: {} }, pdf(), () => undefined, new AbortController().signal);
    lastXhr().finish(403);
    await expect(done).rejects.toThrow(/not accepted/);
  });

  it("runs ticket, upload and finalize in order with an Idempotency-Key", async () => {
    vi.mocked(createUpload).mockResolvedValue({
      upload_id: "u1", url: "https://s3.test/b", fields: {}, expires_at: "2026-01-01T00:00:00Z",
    });
    vi.mocked(finalizeUpload).mockResolvedValue({
      paper: { id: "p1" } as Paper, job: null, duplicate: false,
    });
    const phases: string[] = [];
    const result = uploadPaper(pdf(), { onPhase: (p) => phases.push(p), onProgress: () => undefined, signal: new AbortController().signal });
    await vi.waitFor(() => {
      expect(FakeXhr.last?.body).toBeTruthy();
    });
    lastXhr().finish(204);
    expect((await result).paper.id).toBe("p1");
    expect(phases).toEqual(["checking", "uploading", "starting"]);
    expect(vi.mocked(createUpload).mock.calls[0]?.[1]).toMatch(/^[0-9a-f]{64}$/);
    expect(vi.mocked(finalizeUpload).mock.calls[0]?.[0]).toBe("u1");
    expect(vi.mocked(finalizeUpload).mock.calls[0]?.[1]).toMatch(/^[0-9a-f-]{36}$/);
  });
});
