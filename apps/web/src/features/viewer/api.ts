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
