import { api, apiBaseUrl } from "@/api/client";
import type { components } from "@/api/schema";
import { currentToken, refreshToken } from "@/auth/session";
import { createSseParser } from "@/features/papers/progress";
import { summaryKeys } from "@/features/summaries/api";
import { HttpError } from "@/lib/queryClient";

export type Template = components["schemas"]["TemplateOut"];
export type FieldIn = components["schemas"]["FieldIn"];
export type TemplateIn = components["schemas"]["TemplateIn"];
export type Limits = components["schemas"]["Limits"];
export type FieldStyle = FieldIn["style"];

export const templateKeys = {
  list: summaryKeys.templates, // shared with the template step and the Summary switcher
  detail: (id: string) => ["templates", id] as const,
  limits: ["me", "limits"] as const,
};

/** Saved from an older version (another tab saved first, spec 010 AC10). */
export class StaleTemplateError extends Error {
  constructor(readonly currentVersion: number) {
    super("This template was changed in another tab.");
  }
}

async function problem(response: Response, fallback: string): Promise<HttpError> {
  try {
    const body = (await response.clone().json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail) return new HttpError(response.status, body.detail);
  } catch {
    // not JSON
  }
  return new HttpError(response.status, fallback);
}

export async function getTemplate(id: string): Promise<Template> {
  const { data, response } = await api.GET("/api/v1/templates/{template_id}", { params: { path: { template_id: id } } });
  if (!data) throw await problem(response, "Could not load this template.");
  return data;
}

export async function getLimits(): Promise<Limits> {
  const { data, response } = await api.GET("/api/v1/me/limits");
  if (!data) throw await problem(response, "Could not load your limits.");
  return data;
}

export async function createTemplate(template: TemplateIn): Promise<Template> {
  const { data, response } = await api.POST("/api/v1/templates", { body: { template } });
  if (!data) throw await problem(response, "Could not create the template.");
  return data;
}

export async function duplicateTemplate(id: string): Promise<Template> {
  const { data, response } = await api.POST("/api/v1/templates", { body: { duplicate_of: id } });
  if (!data) throw await problem(response, "Could not duplicate the template.");
  return data;
}

export async function saveTemplate(id: string, baseVersion: number, template: TemplateIn): Promise<Template> {
  const { data, response } = await api.PUT("/api/v1/templates/{template_id}", {
    params: { path: { template_id: id } },
    body: { ...template, base_version: baseVersion },
  });
  if (data) return data;
  if (response.status === 409) {
    const body = (await response.clone().json().catch(() => ({}))) as { current_version?: unknown };
    if (typeof body.current_version === "number") throw new StaleTemplateError(body.current_version);
  }
  throw await problem(response, "Could not save the template.");
}

export async function deleteTemplate(id: string): Promise<void> {
  const { response } = await api.DELETE("/api/v1/templates/{template_id}", { params: { path: { template_id: id } } });
  if (!response.ok) throw await problem(response, "Could not delete the template.");
}

export interface PreviewField {
  key: string;
  value: string;
  status: "found" | "inferred" | "not_reported";
  evidence: { page: number | null; quote: string }[];
}

/** Try a template on a paper (AC7): fields stream in as the model writes them; nothing is saved. */
export async function previewTemplate(
  paperId: string,
  template: TemplateIn,
  onField: (field: PreviewField) => void,
  signal: AbortSignal,
): Promise<void> {
  const send = async (token: string | null) =>
    globalThis.fetch(`${apiBaseUrl}/api/v1/templates/preview`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ paper_id: paperId, template }),
      signal,
    });
  let response = await send(await currentToken());
  if (response.status === 401) response = await send(await refreshToken());
  if (!response.ok || !response.body) throw await problem(response, "Could not run the preview.");
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parse = createSseParser();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    for (const item of parse(value)) {
      if (item.event === "field") onField(JSON.parse(item.data) as PreviewField);
    }
  }
}
