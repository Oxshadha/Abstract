import type { Summary, SummaryField, Template } from "./api";

export const QUICK_ID = "00000000-0000-4000-8000-000000000001";
export const DETAILED_ID = "00000000-0000-4000-8000-000000000002";

export const templates: Template[] = [
  { id: QUICK_ID, kind: "system", name: "Quick Summary", description: "Problem, approach, key findings, and conclusion.", version: 1, version_id: "v1",
    fields: ["abstract", "problem_statement", "methodology", "key_results", "conclusion"].map((key) => ({ key, label: key, instruction: "x", style: "paragraph", required: true })) },
  { id: DETAILED_ID, kind: "system", name: "Detailed Research Analysis", description: "Research gap, methodology, dataset, results, limitations, and future work.", version: 1, version_id: "v2",
    fields: Array.from({ length: 10 }, (_, i) => ({ key: `f${String(i)}`, label: `F${String(i)}`, instruction: "x", style: "paragraph", required: true })) },
];

export function field(overrides: Partial<SummaryField> = {}): SummaryField {
  return {
    key: "problem_statement", label: "Research Problem", style: "paragraph",
    value: "Model long-range dependencies.", status: "found", verification: "verified",
    edited: false, gap_filled: false, evidence: [{ page: 1, quote: "long-range dependencies", verified: true }],
    ...overrides,
  };
}

export function summary(overrides: Partial<Summary> = {}): Summary {
  return {
    id: "s1", paper_id: "p1", template_id: QUICK_ID, template_name: "Quick Summary", template_version: 1,
    status: "ready", coverage: "full", version: 3, seq: 9, title: "Attention Is All You Need",
    authors: ["Ashish Vaswani", "Noam Shazeer"], year: 2017, doc_type: "paper", error_message: null,
    expected_fields: 2, updated_at: new Date().toISOString(),
    fields: [
      field(),
      field({ key: "methodology", label: "Methodology", value: "Self-attention only.", verification: "provisional",
              evidence: [{ page: 2, quote: "invented quote", verified: false }, { page: 3, quote: "x y z", verified: true }] }),
    ],
    ...overrides,
  };
}
