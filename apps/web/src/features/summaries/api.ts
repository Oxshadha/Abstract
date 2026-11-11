import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { HttpError } from "@/lib/queryClient";

export type Template = components["schemas"]["TemplateOut"];
export type Summary = components["schemas"]["SummaryOut"];
export type SummaryField = components["schemas"]["FieldOut"];
export type SummaryBrief = components["schemas"]["SummaryBrief"];

export const summaryKeys = {
  templates: ["templates"] as const,
  forPaper: (paperId: string) => ["papers", paperId, "summaries"] as const,
  detail: (summaryId: string) => ["summaries", summaryId] as const,
};

/** A 412 means the summary changed elsewhere (another tab); the UI offers reload or keep. */
export class StaleVersionError extends Error {}

async function problem(response: Response, fallback: string): Promise<HttpError> {
  try {
    const body = (await response.clone().json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail) return new HttpError(response.status, body.detail);
  } catch {
    // not JSON
  }
  return new HttpError(response.status, fallback);
}

export async function listTemplates(): Promise<Template[]> {
  const { data, response } = await api.GET("/api/v1/templates");
  if (!data) throw await problem(response, "Could not load templates.");
  return data.items;
}

export async function listSummaries(paperId: string): Promise<SummaryBrief[]> {
  const { data, response } = await api.GET("/api/v1/papers/{paper_id}/summaries", {
    params: { path: { paper_id: paperId } },
  });
  if (!data) throw await problem(response, "Could not load summaries.");
  return data.items;
}

export async function createSummary(paperId: string, templateId: string): Promise<SummaryBrief> {
  const { data, response } = await api.POST("/api/v1/papers/{paper_id}/summaries", {
    params: { path: { paper_id: paperId }, header: { "Idempotency-Key": crypto.randomUUID() } },
    body: { template_id: templateId },
  });
  if (!data) throw await problem(response, "Could not start the summary.");
  return data.summary;
}

export async function getSummary(summaryId: string): Promise<Summary> {
  const { data, response } = await api.GET("/api/v1/summaries/{summary_id}", {
    params: { path: { summary_id: summaryId } },
  });
  if (!data) throw await problem(response, "Could not load the summary.");
  return data;
}

export async function editField(summaryId: string, key: string, value: string, version: number): Promise<number> {
  const { data, response } = await api.PATCH("/api/v1/summaries/{summary_id}/fields/{key}", {
    params: { path: { summary_id: summaryId, key }, header: { "If-Match": `"${String(version)}"` } },
    body: { value },
  });
  if (response.status === 412) throw new StaleVersionError("Changed in another tab.");
  if (!data) throw await problem(response, "Could not save your edit.");
  return data.version;
}

export async function resetField(summaryId: string, key: string, version: number): Promise<number> {
  const { data, response } = await api.POST("/api/v1/summaries/{summary_id}/fields/{key}/reset", {
    params: { path: { summary_id: summaryId, key }, header: { "If-Match": `"${String(version)}"` } },
  });
  if (response.status === 412) throw new StaleVersionError("Changed in another tab.");
  if (!data) throw await problem(response, "Could not reset this field.");
  return data.version;
}

export async function retrySummary(summaryId: string): Promise<void> {
  const { response } = await api.POST("/api/v1/summaries/{summary_id}/retry", {
    params: { path: { summary_id: summaryId } },
  });
  if (!response.ok) throw await problem(response, "Could not retry the summary.");
}
