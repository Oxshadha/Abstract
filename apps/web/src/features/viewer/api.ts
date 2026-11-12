import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { HttpError } from "@/lib/queryClient";

export type PageSize = components["schemas"]["PageSize"];

export const viewerKeys = {
  fileUrl: (paperId: string) => ["papers", paperId, "file-url"] as const,
  pages: (paperId: string) => ["papers", paperId, "pages"] as const,
};

export async function getFileUrl(paperId: string): Promise<string> {
  const { data, response } = await api.GET("/api/v1/papers/{paper_id}/file-url", { params: { path: { paper_id: paperId } } });
  if (!data) throw new HttpError(response.status, "The PDF is not available yet.");
  return data.url;
}

export async function getPageSizes(paperId: string): Promise<PageSize[]> {
  const { data, response } = await api.GET("/api/v1/papers/{paper_id}/pages", { params: { path: { paper_id: paperId } } });
  if (!data) throw new HttpError(response.status, "Could not load the page sizes.");
  return data.items;
}

export type Elements = components["schemas"]["ElementsOut"];
export type TableEl = components["schemas"]["TableOut"];
export type FigureEl = components["schemas"]["FigureOut"];

export const elementKeys = {
  list: (paperId: string) => ["papers", paperId, "elements"] as const,
  image: (paperId: string, figureId: string) => ["papers", paperId, "figures", figureId, "image"] as const,
};

export async function getElements(paperId: string): Promise<Elements> {
  const { data, response } = await api.GET("/api/v1/papers/{paper_id}/elements", { params: { path: { paper_id: paperId } } });
  if (!data) throw new HttpError(response.status, "Could not load the tables and figures.");
  return data;
}

export async function getFigureImage(paperId: string, figureId: string): Promise<string> {
  const { data, response } = await api.GET("/api/v1/papers/{paper_id}/figures/{figure_id}/image", {
    params: { path: { paper_id: paperId, figure_id: figureId } },
  });
  if (!data) throw new HttpError(response.status, "The figure image is not available.");
  return data.url;
}

export async function describeFigure(paperId: string, figureId: string): Promise<string> {
  const { data, response } = await api.POST("/api/v1/papers/{paper_id}/figures/{figure_id}/describe", {
    params: { path: { paper_id: paperId, figure_id: figureId } },
  });
  if (!data) throw new HttpError(response.status, "Could not describe this figure right now.");
  return data.description;
}

export async function retryEnrichment(paperId: string): Promise<void> {
  const { response } = await api.POST("/api/v1/papers/{paper_id}/enrichment/retry", { params: { path: { paper_id: paperId } } });
  if (!response.ok) throw new HttpError(response.status, "Could not start again. Please try in a moment.");
}
