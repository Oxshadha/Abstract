import { createUpload, finalizeUpload, type FinalizeResponse, type UploadTicket } from "./api";

/**
 * Mirrors the server default (spec 004 AC1) so users hear about it before uploading; the server
 * enforces the real limit, which moves to entitlements with plans (spec 012).
 */
export const UPLOAD_MAX_BYTES = 50 * 1024 * 1024;

export type UploadPhase = "checking" | "uploading" | "starting";

export class UploadError extends Error {}

export class UploadCancelledError extends Error {
  constructor() {
    super("Upload cancelled.");
  }
}

/** AC2: reject non-PDF and oversize files before anything is sent. */
export function validatePdf(file: File): string | null {
  const looksPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!looksPdf) return "Please choose a PDF file.";
  if (file.size === 0) return "This file is empty.";
  if (file.size > UPLOAD_MAX_BYTES) return "This PDF is larger than 50 MB.";
  return null;
}

/** SHA-256 in the browser, for instant per-user dedupe (verified again by the worker). */
export async function sha256Hex(file: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Direct browser-to-storage POST with progress (fetch has no upload progress, so XHR). */
export function postToStorage(
  ticket: Pick<UploadTicket, "url" | "fields">,
  file: File,
  onProgress: (fraction: number) => void,
  signal: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    for (const [name, value] of Object.entries(ticket.fields)) form.append(name, value);
    form.append("file", file); // must be the last field of an S3 POST form
    const xhr = new XMLHttpRequest();
    xhr.open("POST", ticket.url);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new UploadError("The upload was not accepted. Please try again."));
    };
    xhr.onerror = () => {
      reject(new UploadError("The upload failed. Check your connection and try again."));
    };
    xhr.onabort = () => {
      reject(new UploadCancelledError());
    };
    if (signal.aborted) {
      reject(new UploadCancelledError());
      return;
    }
    signal.addEventListener("abort", () => {
      xhr.abort();
    });
    xhr.send(form);
  });
}

export interface UploadCallbacks {
  onPhase: (phase: UploadPhase) => void;
  onProgress: (fraction: number) => void;
  signal: AbortSignal;
}

/** The whole AC2 flow: check, hash, ticket, direct upload, finalize (with an Idempotency-Key). */
export async function uploadPaper(file: File, { onPhase, onProgress, signal }: UploadCallbacks): Promise<FinalizeResponse> {
  const invalid = validatePdf(file);
  if (invalid) throw new UploadError(invalid);
  onPhase("checking");
  const sha256 = await sha256Hex(file);
  if (signal.aborted) throw new UploadCancelledError();
  const ticket = await createUpload(file, sha256);
  onPhase("uploading");
  await postToStorage(ticket, file, onProgress, signal);
  onPhase("starting");
  return finalizeUpload(ticket.upload_id, crypto.randomUUID());
}
