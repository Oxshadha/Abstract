import { MoreHorizontal } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { FLOATING_STYLE, useFloating } from "./useFloating";

export interface MenuItem {
  label: string;
  icon?: ReactNode;
  onSelect: () => void;
  checked?: boolean; // shown as a checkmark item (menuitemcheckbox)
  disabled?: boolean;
  destructive?: boolean; // Delete, Sign out: red text and icon (D84)
}

interface Props {
  label: string; // accessible name of the trigger, e.g. "Actions for Attention Is All You Need"
  items: MenuItem[];
  footer?: ReactNode;
  align?: "left" | "right";
  trigger?: ReactNode;
}

/**
 * The app's action menu ("..." on rows and collections). Arrow keys, Home/End, Enter and
 * Escape work as in a native menu; clicking outside closes it; focus returns to the trigger.
 */
export function Menu({ label, items, footer, align = "right", trigger }: Props) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const dismiss = useCallback(() => { setOpen(false); }, []);
  const panel = useRef<HTMLDivElement>(null);
  useFloating(open, button, panel, align, dismiss);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!root.current?.contains(target) && !panel.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    refs.current.find((el) => el && !el.disabled)?.focus();
    return () => { document.removeEventListener("mousedown", close); };
  }, [open]);

  const focusAt = (index: number) => {
    const enabled = refs.current.filter((el): el is HTMLButtonElement => Boolean(el && !el.disabled));
    const current = enabled.indexOf(document.activeElement as HTMLButtonElement);
    const next = index === Infinity ? enabled.length - 1 : index === -Infinity ? 0 : (current + index + enabled.length) % enabled.length;
    enabled[next]?.focus();
  };
  const onKey = (event: KeyboardEvent) => {
    const moves: Record<string, number> = { ArrowDown: 1, ArrowUp: -1, Home: -Infinity, End: Infinity };
    const move = moves[event.key];
    if (move !== undefined) {
      event.preventDefault();
      focusAt(move);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      button.current?.focus();
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  };

  return (
    <div ref={root} className="relative">
      <button
        ref={button}
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => { setOpen(!open); }}
        className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted"
      >
        {trigger ?? <MoreHorizontal aria-hidden className="size-5" />}
      </button>
      {open && createPortal(
        <div
          ref={panel}
          role="menu"
          aria-label={label}
          onKeyDown={onKey}
          style={FLOATING_STYLE}
          className="z-50 w-60 overflow-auto rounded-lg border border-border bg-surface p-1 shadow-overlay"
        >
          {items.map((item, i) => (
            <button
              key={item.label}
              ref={(el) => { refs.current[i] = el; }}
              type="button"
              role={item.checked === undefined ? "menuitem" : "menuitemcheckbox"}
              aria-checked={item.checked}
              disabled={item.disabled}
              onClick={() => {
                setOpen(false);
                button.current?.focus();
                item.onSelect();
              }}
              className={`flex min-h-11 w-full items-center gap-2 rounded-md px-2 text-left text-sm hover:bg-muted focus-visible:bg-muted disabled:opacity-50 ${item.destructive ? "text-error" : ""}`}
            >
              {item.icon}
              <span className="min-w-0 flex-1 truncate">{item.label}</span>
            </button>
          ))}
          {footer}
        </div>,
        document.body,
      )}
    </div>
  );
}
