import type { Paper } from "@/features/papers/api";

export function paperName(paper: Paper): string {
  return paper.title ?? paper.filename;
}
