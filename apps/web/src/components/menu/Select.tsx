import { Check, ChevronDown } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { FLOATING_STYLE, useFloating } from "./useFloating";

export interface SelectOption<T extends string> {
  value: T;
  label: string;
  description?: string;
}

interface Props<T extends string> {
  label: string; // accessible name of the list
  value: T;
  options: SelectOption<T>[];
  onChange: (value: T) => void;
  icon?: ReactNode;
  align?: "left" | "right";
  className?: string;
  footer?: ReactNode; // e.g. a link below the options
  width?: string;
  placeholder?: string; // shown when no option matches `value`
}

/**
 * The app's dropdown (replaces native <select>, which looks different in every browser).
 * A button opens a listbox; arrow keys, Home/End, Enter and Escape work as in a native select;
 * clicking outside closes it.
 */
export function Select<T extends string>({
  label, value, options, onChange, icon, align = "right", className = "", footer, width = "w-56", placeholder = "",
}: Props<T>) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();
  const current = options.find((o) => o.value === value);
  const dismiss = useCallback(() => { setOpen(false); }, []);
  const panel = useRef<HTMLDivElement>(null);
  useFloating(open, trigger, panel, align, dismiss);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!root.current?.contains(target) && !panel.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    list.current?.focus();
    return () => { document.removeEventListener("mousedown", close); };
  }, [open]);

  const show = () => {
    setActive(Math.max(0, options.findIndex((o) => o.value === value)));
    setOpen(true);
  };
  const choose = (option: SelectOption<T>) => {
    setOpen(false);
    trigger.current?.focus();
    if (option.value !== value) onChange(option.value);
  };
  const onListKey = (event: KeyboardEvent) => {
    const last = options.length - 1;
    const keys: Record<string, () => void> = {
      ArrowDown: () => { setActive((a) => Math.min(last, a + 1)); },
      ArrowUp: () => { setActive((a) => Math.max(0, a - 1)); },
      Home: () => { setActive(0); },
      End: () => { setActive(last); },
      Enter: () => { const o = options[active]; if (o) choose(o); },
      " ": () => { const o = options[active]; if (o) choose(o); },
      Escape: () => { setOpen(false); trigger.current?.focus(); },
      Tab: () => { setOpen(false); },
    };
    const action = keys[event.key];
    if (action) {
      if (event.key !== "Tab") event.preventDefault();
      action();
    }
  };

  return (
    <div ref={root} className={`relative ${className}`}>
      <button
        ref={trigger}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => { if (open) setOpen(false); else show(); }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); show(); }
        }}
        className="inline-flex min-h-11 min-w-0 items-center gap-2 rounded-md border border-border bg-surface px-3 text-sm hover:bg-muted"
      >
        {icon}
        <span className="sr-only">{`${label}: `}</span>
        <span className="truncate whitespace-nowrap">{current?.label ?? placeholder}</span>
        <ChevronDown aria-hidden className={`size-4 shrink-0 transition-transform motion-reduce:transition-none ${open ? "rotate-180" : ""}`} />
      </button>
      {open && createPortal(
        <div ref={panel} style={FLOATING_STYLE} className={`z-50 flex flex-col ${width} rounded-lg border border-border bg-surface p-1 shadow-overlay`}>
          <ul
            ref={list}
            id={id}
            role="listbox"
            aria-label={label}
            tabIndex={-1}
            aria-activedescendant={`${id}-${String(active)}`}
            onKeyDown={onListKey}
            className="max-h-80 min-h-0 overflow-auto outline-none"
          >
            {options.map((option, i) => (
              <li
                key={option.value}
                id={`${id}-${String(i)}`}
                role="option"
                aria-selected={option.value === value}
                onMouseEnter={() => { setActive(i); }}
                onClick={() => { choose(option); }}
                className={`flex min-h-11 cursor-pointer items-start gap-2 rounded-md px-2 py-2.5 text-sm ${i === active ? "bg-muted" : ""}`}
              >
                <Check aria-hidden className={`mt-0.5 size-4 shrink-0 ${option.value === value ? "" : "invisible"}`} />
                <span className="min-w-0">
                  <span className={`block ${option.description ? "font-medium" : ""}`}>{option.label}</span>
                  {option.description && <span className="block text-text-secondary">{option.description}</span>}
                </span>
              </li>
            ))}
          </ul>
          {footer}
        </div>,
        document.body,
      )}
    </div>
  );
}
