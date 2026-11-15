import { Toaster as SonnerToaster } from "sonner";

/** App-wide toasts, styled only through design tokens (D44, spec 003 AC5). */
export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-right"
      // Phones: above the floating navigation pill (design principle 3), not over it.
      mobileOffset={{ bottom: 96 }}
      closeButton
      toastOptions={{
        unstyled: true,
        classNames: {
          toast:
            "flex w-full items-start gap-3 rounded-lg border border-border bg-surface p-4 text-text shadow-overlay",
          title: "font-medium",
          description: "text-sm text-text-secondary",
          success: "[&_[data-icon]]:text-success",
          error: "[&_[data-icon]]:text-error",
          warning: "[&_[data-icon]]:text-warning",
          info: "[&_[data-icon]]:text-info",
          closeButton: "text-text-secondary",
          // Undo after deleting (spec 019 AC2): a plain text button, 44 px tall to tap.
          actionButton: "ml-auto -my-2 min-h-11 shrink-0 rounded-md px-3 font-medium underline hover:bg-muted",
        },
      }}
    />
  );
}

