import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { problem } from "@/lib/problem";

export type Notes = components["schemas"]["Notes"];
export type NotesDoc = Notes["doc"];

export const MAX_NOTES_CHARS = 50_000;

export const notesKeys = {
  forPaper: (paperId: string) => ["papers", paperId, "notes"] as const,
};

/** A 409: the notes were saved elsewhere (another tab, or Save to notes) since they were loaded. */
export class NotesChangedError extends Error {}

export async function getNotes(paperId: string): Promise<Notes> {
  const { data, response } = await api.GET("/api/v1/papers/{paper_id}/notes", {
    params: { path: { paper_id: paperId } },
  });
  if (!data) throw await problem(response, "Could not load your notes.");
  return data;
}

export async function saveNotes(paperId: string, doc: NotesDoc, baseVersion: number): Promise<Notes> {
  const { data, response } = await api.PUT("/api/v1/papers/{paper_id}/notes", {
    params: { path: { paper_id: paperId } },
    body: { doc, base_version: baseVersion },
  });
  if (response.status === 409) throw new NotesChangedError("Changed in another tab.");
  if (!data) throw await problem(response, "Could not save your notes.");
  return data;
}

/** Spec 014 AC2: add a chat answer, with its question and page sources, to the notes. */
export async function saveAnswer(paperId: string, messageId: string): Promise<Notes> {
  const { data, response } = await api.POST("/api/v1/papers/{paper_id}/notes/answers", {
    params: { path: { paper_id: paperId } },
    body: { message_id: messageId },
  });
  if (!data) throw await problem(response, "Could not save this answer to your notes.");
  return data;
}
