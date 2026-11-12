import { api } from "@/api/client";
import type { components } from "@/api/schema";
import type { Paper, PaperPage } from "@/features/papers/api";
import { HttpError } from "@/lib/queryClient";

export type Collection = components["schemas"]["CollectionOut"];
export type SearchResults = components["schemas"]["SearchResults"];
export type Sort = "added" | "opened" | "title";
export type DocType = "paper" | "report" | "article";

export interface LibraryParams {
  sort: Sort;
  type?: DocType;
  starred?: boolean;
  collection?: string;
}

export const PAGE_SIZE = 30;

/** All list and detail keys start with "papers", so one invalidation refreshes every view. */
export const libraryKeys = {
  list: (params: LibraryParams) => ["papers", "list", params] as const,
  recent: ["papers", "list", "recent"] as const,
  collections: ["collections"] as const,
  paperCollections: (paperId: string) => ["collections", "paper", paperId] as const,
  search: (q: string, collection: string | null) => ["search", q, collection] as const,
};

async function problem(response: Response, fallback: string): Promise<HttpError> {
  try {
    const body = (await response.clone().json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail) return new HttpError(response.status, body.detail);
  } catch {
    // not JSON
  }
  return new HttpError(response.status, fallback);
}

export async function listLibrary(params: LibraryParams, cursor: string | null, signal?: AbortSignal, limit = PAGE_SIZE): Promise<PaperPage> {
  const { data, response } = await api.GET("/api/v1/papers", {
    params: {
      query: {
        limit,
        sort: params.sort,
        ...(params.type ? { type: params.type } : {}),
        ...(params.starred ? { starred: true } : {}),
        ...(params.collection ? { collection: params.collection } : {}),
        ...(cursor ? { cursor } : {}),
      },
    },
    signal,
  });
  if (!data) throw await problem(response, "Could not load your papers.");
  return data;
}

export async function updatePaper(paperId: string, body: { title?: string; starred?: boolean }): Promise<Paper> {
  const { data, response } = await api.PATCH("/api/v1/papers/{paper_id}", { params: { path: { paper_id: paperId } }, body });
  if (!data) throw await problem(response, "Could not update the paper.");
  return data;
}

export async function markOpened(paperId: string): Promise<void> {
  await api.POST("/api/v1/papers/{paper_id}/opened", { params: { path: { paper_id: paperId } } });
}

export async function listCollections(): Promise<Collection[]> {
  const { data, response } = await api.GET("/api/v1/collections");
  if (!data) throw await problem(response, "Could not load your collections.");
  return data.items;
}

export async function createCollection(name: string): Promise<Collection> {
  const { data, response } = await api.POST("/api/v1/collections", { body: { name } });
  if (!data) throw await problem(response, "Could not create the collection.");
  return data;
}

export async function renameCollection(id: string, name: string): Promise<Collection> {
  const { data, response } = await api.PATCH("/api/v1/collections/{collection_id}", {
    params: { path: { collection_id: id } },
    body: { name },
  });
  if (!data) throw await problem(response, "Could not rename the collection.");
  return data;
}

export async function deleteCollection(id: string): Promise<void> {
  const { response } = await api.DELETE("/api/v1/collections/{collection_id}", { params: { path: { collection_id: id } } });
  if (!response.ok) throw await problem(response, "Could not delete the collection.");
}

export async function setMembership(collectionId: string, paperId: string, member: boolean): Promise<void> {
  const params = { params: { path: { collection_id: collectionId, paper_id: paperId } } };
  const { response } = member
    ? await api.PUT("/api/v1/collections/{collection_id}/papers/{paper_id}", params)
    : await api.DELETE("/api/v1/collections/{collection_id}/papers/{paper_id}", params);
  if (!response.ok) throw await problem(response, "Could not update the collection.");
}

export async function paperCollections(paperId: string): Promise<string[]> {
  const { data, response } = await api.GET("/api/v1/papers/{paper_id}/collections", { params: { path: { paper_id: paperId } } });
  if (!data) throw await problem(response, "Could not load the paper's collections.");
  return data;
}

export async function searchPapers(q: string, collection: string | null, signal?: AbortSignal): Promise<SearchResults> {
  const { data, response } = await api.GET("/api/v1/search", {
    params: { query: { q, ...(collection ? { collection } : {}) } },
    signal,
  });
  if (!data) throw await problem(response, "Search is not available right now.");
  return data;
}
