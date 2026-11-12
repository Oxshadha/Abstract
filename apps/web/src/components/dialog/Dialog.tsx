import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";

interface Props {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}

/**
 * The app's modal, on the native <dialog> (focus is kept inside, Escape closes, the page
 * behind is inert in every current browser). Styled only with tokens.
 */
export function Dialog({ open, title, onClose, children, footer }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const el = ref.current as (Partial<HTMLDialogElement> & HTMLElement) | null;
    if (!el) return;
    if (open && !el.hasAttribute("open")) {
      if (typeof el.showModal === "function") el.showModal();
      else el.setAttribute("open", ""); // test environments without <dialog> support
    } else if (!open && el.hasAttribute("open")) {
      if (typeof el.close === "function") el.close();
      else el.removeAttribute("open");
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === ref.current) onClose(); // click on the backdrop
      }}
      className="m-auto w-[calc(100%-2rem)] max-w-md rounded-xl border border-border bg-surface p-0 text-text shadow-overlay backdrop:bg-text/40"
    >
      {open && (
        <div className="flex flex-col gap-4 p-5">
          <div className="flex items-center gap-2">
            <h2 id={titleId} className="font-display text-lg font-bold">{title}</h2>
            <button type="button" aria-label="Close" onClick={onClose} className="ml-auto inline-flex size-11 items-center justify-center rounded-md hover:bg-muted">
              <X aria-hidden className="size-5" />
            </button>
          </div>
          {children}
          {footer && <div className="flex justify-end gap-2">{footer}</div>}
        </div>
      )}
    </dialog>
  );
}

export const buttonPrimary =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-pill bg-primary px-5 font-medium text-primary-text disabled:opacity-50";
export const buttonSecondary =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-pill border border-border px-5 hover:bg-muted";
export const inputClass =
  "min-h-11 w-full rounded-md border border-border bg-surface px-3 text-text placeholder:text-text-secondary";
