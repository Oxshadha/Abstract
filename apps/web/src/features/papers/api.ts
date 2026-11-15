import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { problem } from "@/lib/problem";

export type Paper = components["schemas"]["PaperOut"];
export type PaperPage = components["schemas"]["PaperPage"];
export type PaperStatus = components["schemas"]["PaperStatus"];
export type UploadTicket = components["schemas"]["UploadTicket"];
export type FinalizeResponse = components["schemas"]["FinalizeResponse"];

export const paperKeys = {
  list: ["papers"] as const,
  detail: (id: string) => ["papers", id] as const,
  status: (id: string) => ["papers", id, "status"] as const,
};

/** problem+json `detail` is written for users (spec 001 AC5); fall back to a calm default. */

export async function listPapers(cursor: string | null): Promise<PaperPage> {
  const { data, response } = await api.GET("/api/v1/papers", {
    params: { query: { limit: 20, ...(cursor ? { cursor } : {}) } },
  });
  if (!data) throw await problem(response, "Could not load your papers.");
  return data;
}

export async function getPaper(paperId: string): Promise<Paper> {
  const { data, response } = await api.GET("/api/v1/papers/{paper_id}", {
    params: { path: { paper_id: paperId } },
  });
  if (!data) throw await problem(response, "Could not load this paper.");
  return data;
}

export async function getStatus(paperId: string): Promise<PaperStatus> {
  const { data, response } = await api.GET("/api/v1/papers/{paper_id}/status", {
    params: { path: { paper_id: paperId } },
  });
  if (!data) throw await problem(response, "Could not load the processing status.");
  return data;
}

export async function createUpload(file: File, sha256: string): Promise<UploadTicket> {
  const { data, response } = await api.POST("/api/v1/papers/uploads", {
    body: { filename: file.name.slice(0, 255), size_bytes: file.size, sha256, content_type: "application/pdf" },
  });
  if (!data) throw await problem(response, "Could not start the upload.");
  return data;
}

/** The PDF matches a paper in Recently deleted (spec 019 AC8): the reader chooses what to do. */
export class PaperInTrashError extends Error {
  constructor(
    readonly uploadId: string,
    readonly paperId: string,
    readonly title: string,
  ) {
    super("This paper is in Recently deleted.");
  }
}

export async function finalizeUpload(uploadId: string, idempotencyKey: string): Promise<FinalizeResponse> {
  const { data, error, response } = await api.POST("/api/v1/papers", {
    body: { upload_id: uploadId },
    params: { header: { "Idempotency-Key": idempotencyKey } },
  });
  if (!data) {
    // The client has already read the body into `error`; reading the response again would fail.
    const body = error as { type?: string; paper_id?: string; title?: string };
    if (response.status === 409 && body.type?.endsWith("/paper-in-trash") && body.paper_id) throw new PaperInTrashError(uploadId, body.paper_id, body.title ?? "This paper");
    throw await problem(response, "Could not finish the upload.");
  }
  return data;
}

export async function deletePaper(paperId: string): Promise<void> {
  const { response } = await api.DELETE("/api/v1/papers/{paper_id}", {
    params: { path: { paper_id: paperId } },
  });
  if (!response.ok) throw await problem(response, "Could not delete this paper.");
}
