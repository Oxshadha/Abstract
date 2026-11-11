import { Toaster as SonnerToaster } from "sonner";

/** App-wide toasts, styled only through design tokens (D44, spec 003 AC5). */
export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-right"
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
        },
      }}
    />
  );
}

