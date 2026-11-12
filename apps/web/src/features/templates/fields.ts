import type { FieldIn, FieldStyle, Limits, Template, TemplateIn } from "./api";

/** A field as the builder edits it; `id` is local (React keys, drag ids), `key` is the saved key. */
export interface DraftField {
  id: string;
  key?: string | null;
  label: string;
  instruction: string;
  style: FieldStyle;
  required: boolean;
}

export interface Draft {
  name: string;
  description: string;
  fields: DraftField[];
}

export const STYLES: { value: FieldStyle; label: string }[] = [
  { value: "paragraph", label: "Paragraph" },
  { value: "bullets", label: "Bullets" },
  { value: "short", label: "Short value" },
];

export function newField(): DraftField {
  return { id: crypto.randomUUID(), key: null, label: "", instruction: "", style: "paragraph", required: true };
}

export function fromTemplate(t: Template): Draft {
  return {
    name: t.name,
    description: t.description,
    fields: t.fields.map((f) => ({ id: crypto.randomUUID(), key: f.key, label: f.label, instruction: f.instruction, style: f.style, required: f.required })),
  };
}

export function toTemplateIn(d: Draft): TemplateIn {
  return {
    name: d.name.trim(),
    description: d.description.trim(),
    fields: d.fields.map<FieldIn>((f) => ({
      ...(f.key ? { key: f.key } : {}),
      label: f.label.trim(),
      instruction: f.instruction.trim(),
      style: f.style,
      required: f.required,
    })),
  };
}

export interface Problems {
  name?: string;
  form?: string;
  fields: Record<string, { label?: string; instruction?: string }>;
}

/** AC9: the same limits the API enforces, checked before submit. */
export function validate(d: Draft, limits: Limits): Problems {
  const problems: Problems = { fields: {} };
  if (!d.name.trim()) problems.name = "Give the template a name.";
  else if (d.name.trim().length > 80) problems.name = "Names can be up to 80 characters.";
  if (d.fields.length === 0) problems.form = "Add at least one field.";
  if (d.fields.length > limits.fields_per_template) problems.form = `A template can have up to ${String(limits.fields_per_template)} fields.`;
  const seen = new Map<string, string>();
  for (const f of d.fields) {
    const p: { label?: string; instruction?: string } = {};
    const label = f.label.trim();
    if (!label) p.label = "Add a label.";
    else if (label.length > limits.label_chars) p.label = `Labels can be up to ${String(limits.label_chars)} characters.`;
    else if (seen.has(label.toLowerCase())) p.label = "Another field has this label.";
    seen.set(label.toLowerCase(), f.id);
    if (!f.instruction.trim()) p.instruction = "Say what this field should contain.";
    else if (f.instruction.trim().length > limits.instruction_chars) p.instruction = `Instructions can be up to ${String(limits.instruction_chars)} characters.`;
    if (p.label || p.instruction) problems.fields[f.id] = p;
  }
  return problems;
}

export function hasProblems(p: Problems): boolean {
  return Boolean(p.name ?? p.form) || Object.keys(p.fields).length > 0;
}

/** AC12: a small, readable file; keys are not exported (they are made again on import). */
export function exportJson(d: Draft): string {
  const t = toTemplateIn(d);
  return JSON.stringify({ format: "abstract-template", version: 1, name: t.name, description: t.description, fields: t.fields.map(({ label, instruction, style, required }) => ({ label, instruction, style, required })) }, null, 2);
}

/** Parse an exported file; unknown or malformed content is rejected with a reason. */
export function importJson(text: string): Draft {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    throw new Error("This file is not a template export.");
  }
  if (typeof raw !== "object" || raw === null) throw new Error("This file is not a template export.");
  const obj = raw as Record<string, unknown>;
  if (obj.format !== "abstract-template" || !Array.isArray(obj.fields)) throw new Error("This file is not a template export.");
  const styles = new Set(STYLES.map((s) => s.value));
  const fields = obj.fields.map((item): DraftField => {
    const f = (typeof item === "object" && item !== null ? item : {}) as Record<string, unknown>;
    const style = typeof f.style === "string" && styles.has(f.style as FieldStyle) ? (f.style as FieldStyle) : "paragraph";
    return {
      id: crypto.randomUUID(),
      key: null,
      label: typeof f.label === "string" ? f.label : "",
      instruction: typeof f.instruction === "string" ? f.instruction : "",
      style,
      required: f.required !== false,
    };
  });
  return { name: typeof obj.name === "string" ? obj.name : "Imported template", description: typeof obj.description === "string" ? obj.description : "", fields };
}
