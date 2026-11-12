import { useId, type ReactNode } from "react";

import { inputClass } from "@/components/dialog/Dialog";

/** The app's on/off switch (same look as the template builder). */
export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (next: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => { onChange(!checked); }}
      className="inline-flex size-11 shrink-0 items-center justify-center rounded-md hover:bg-muted disabled:opacity-50"
    >
      <span aria-hidden className={`relative h-6 w-10 rounded-pill transition-colors motion-reduce:transition-none ${checked ? "bg-primary" : "bg-muted"}`}>
        <span className={`absolute top-0.5 left-0.5 size-5 rounded-pill bg-surface shadow-card transition-transform motion-reduce:transition-none ${checked ? "translate-x-4" : "translate-x-0"}`} />
      </span>
    </button>
  );
}

export function Card({ title, action, children, className = "" }: { title: string; action?: ReactNode; children: ReactNode; className?: string }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={`flex min-w-0 flex-col gap-3 rounded-lg border border-border bg-surface p-4 ${className}`}>
      <div className="flex min-w-0 items-center gap-2">
        <h2 id={id} className="min-w-0 flex-1 truncate font-display text-base font-bold">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

/** A number typed as text (no native spinners, design principle 11); empty means "No limit". */
export function NumberField({ label, value, onChange, allowEmpty, step = "whole" }: {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  allowEmpty?: boolean;
  step?: "whole" | "money";
}) {
  const id = useId();
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className="text-xs text-text-secondary">{label}</label>
      <input
        id={id}
        type="text"
        inputMode={step === "money" ? "decimal" : "numeric"}
        value={value === null ? "" : String(value)}
        placeholder={allowEmpty ? "No limit" : undefined}
        onChange={(e) => {
          const raw = e.target.value.trim();
          if (raw === "") {
            onChange(allowEmpty ? null : 0);
            return;
          }
          const n = step === "money" ? Number.parseFloat(raw) : Number.parseInt(raw, 10);
          if (Number.isFinite(n)) onChange(n);
        }}
        className={`${inputClass} tabular-nums`}
      />
    </div>
  );
}
