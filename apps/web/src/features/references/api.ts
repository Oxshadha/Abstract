import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { problem } from "@/lib/problem";

export type References = components["schemas"]["References"];
export type ReferenceItem = components["schemas"]["ReferenceItem"];

export const referenceKeys = {
  forPaper: (paperId: string) => ["papers", paperId, "references"] as const,
};

export async function getReferences(paperId: string): Promise<References> {
  const { data, response } = await api.GET("/api/v1/papers/{paper_id}/references", {
    params: { path: { paper_id: paperId } },
  });
  if (!data) throw await problem(response, "Could not load the references.");
  return data;
}
