import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ArrowDown, ArrowUp, Copy, GripVertical, Trash2 } from "lucide-react";
import { useId } from "react";

import { inputClass } from "@/components/dialog/Dialog";
import { Menu } from "@/components/menu/Menu";
import { Select } from "@/components/menu/Select";
import { FieldError } from "@/components/status/FieldError";

import type { FieldStyle, Limits } from "./api";
import { STYLES, type DraftField } from "./fields";

interface Props {
  field: DraftField;
  index: number;
  count: number;
  limits: Limits;
  problem?: { label?: string; instruction?: string };
  onChange: (field: DraftField) => void;
  onMove: (from: number, to: number) => void;
  onDuplicate: () => void;
  onRemove: () => void;
  canAdd: boolean;
}

/** One field of a template (spec 010 AC3): drag (or arrows on phones) to reorder. */
export function FieldCard({ field, index, count, limits, problem, onChange, onMove, onDuplicate, onRemove, canAdd }: Props) {
  const { setNodeRef, transform, transition, attributes, listeners, isDragging } = useSortable({ id: field.id });
  const labelId = useId();
  const instructionId = useId();
  const name = field.label.trim() || `Field ${String(index + 1)}`;
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`flex gap-2 rounded-lg border border-border bg-surface p-3 ${isDragging ? "relative z-10 shadow-overlay" : ""}`}
    >
      <div className="flex flex-col items-center gap-1">
        <button
          type="button"
          aria-label={`Drag to reorder ${name}`}
          title="Drag to reorder"
          {...attributes}
          {...listeners}
          className="hidden size-11 cursor-grab touch-none items-center justify-center rounded-md text-text-secondary hover:bg-muted active:cursor-grabbing sm:inline-flex"
        >
          <GripVertical aria-hidden className="size-5" />
        </button>
        {/* Phones: explicit up and down instead of dragging (D60). */}
        <button type="button" aria-label={`Move ${name} up`} disabled={index === 0} onClick={() => { onMove(index, index - 1); }} className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted disabled:opacity-30 sm:hidden">
          <ArrowUp aria-hidden className="size-4" />
        </button>
        <button type="button" aria-label={`Move ${name} down`} disabled={index === count - 1} onClick={() => { onMove(index, index + 1); }} className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted disabled:opacity-30 sm:hidden">
          <ArrowDown aria-hidden className="size-4" />
        </button>
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <label htmlFor={labelId} className="sr-only">{`Label of field ${String(index + 1)}`}</label>
            <input
              id={labelId}
              value={field.label}
              maxLength={limits.label_chars}
              placeholder="Label, for example Dataset"
              aria-invalid={problem?.label ? true : undefined}
              aria-describedby={problem?.label ? `${labelId}-error` : undefined}
              onChange={(e) => { onChange({ ...field, label: e.target.value }); }}
              className={`${inputClass} font-medium`}
            />
            <FieldError id={`${labelId}-error`} message={problem?.label} />
          </div>
          <Menu
            label={`Actions for ${name}`}
            items={[
              { label: "Duplicate", icon: <Copy aria-hidden className="size-4" />, onSelect: onDuplicate, disabled: !canAdd },
              { label: "Remove", icon: <Trash2 aria-hidden className="size-4" />, destructive: true, onSelect: onRemove },
            ]}
          />
        </div>
        <div>
          <label htmlFor={instructionId} className="sr-only">{`What ${name} should contain`}</label>
          <textarea
            id={instructionId}
            value={field.instruction}
            maxLength={limits.instruction_chars}
            rows={2}
            placeholder="What should this field contain? For example: the datasets used, with their sizes."
            aria-invalid={problem?.instruction ? true : undefined}
            aria-describedby={`${instructionId}-count${problem?.instruction ? ` ${instructionId}-error` : ""}`}
            onChange={(e) => { onChange({ ...field, instruction: e.target.value }); }}
            className={`${inputClass} min-h-20 resize-y py-2`}
          />
          <div className="flex items-start justify-between gap-2">
            <FieldError id={`${instructionId}-error`} message={problem?.instruction} />
            <span id={`${instructionId}-count`} className="ml-auto text-xs text-text-secondary tabular-nums">
              {`${String(field.instruction.length)}/${String(limits.instruction_chars)}`}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select<FieldStyle>
            label="Output style"
            value={field.style}
            options={STYLES}
            onChange={(style) => { onChange({ ...field, style }); }}
            align="left"
            width="w-44"
          />
          <button
            type="button"
            role="switch"
            aria-checked={field.required}
            onClick={() => { onChange({ ...field, required: !field.required }); }}
            className="inline-flex min-h-11 items-center gap-2 rounded-md px-2 text-sm hover:bg-muted"
          >
            <span aria-hidden className={`relative h-6 w-10 rounded-pill transition-colors motion-reduce:transition-none ${field.required ? "bg-primary" : "bg-muted"}`}>
              <span className={`absolute top-0.5 left-0.5 size-5 rounded-pill bg-surface shadow-card transition-transform motion-reduce:transition-none ${field.required ? "translate-x-4" : "translate-x-0"}`} />
            </span>
            Required
          </button>
        </div>
      </div>
    </li>
  );
}
