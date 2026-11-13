import { lazy, Suspense } from "react";

import { useMediaQuery } from "@/features/workspace/layout";

import { AuthPanel } from "./AuthPanel";

// WebGL wordmark, loaded only on desktop where the hero is shown (D96).
const LiquidText = lazy(() => import("@/components/brand/LiquidText").then((m) => ({ default: m.LiquidText })));

const WIDE = "(min-width: 1024px)";

/** The liquid "abstract." wordmark beside the form, desktop only (D96). */
function AuthHero({ page }: { page: boolean }) {
  // The standalone page needs its own h1; inside the dialog the form title names it.
  const Tagline = page ? "h1" : "p";
  return (
    <section aria-label="Abstract" className="flex min-w-0 flex-col justify-center gap-4 border-r border-border p-10">
      <Suspense fallback={<div className="h-40" />}>
        <LiquidText text="abstract." fontSize={150} />
      </Suspense>
      <Tagline className="text-center font-display text-xl font-medium">Research papers, made clear.</Tagline>
      <p className="mx-auto max-w-sm text-center text-sm text-text-secondary">
        Structured summaries, answers with page citations and your own templates, all from the paper itself.
      </p>
    </section>
  );
}

/**
 * Sign-in card shared by the dialog over the blurred app and the sign-in and sign-up routes.
 * Desktop: two columns, the liquid wordmark and the form. Phones: the form only, as before.
 */
export function AuthCard({ mode, routing }: { mode: "sign-in" | "sign-up"; routing: "hash" | "path" }) {
  const page = routing === "path";
  const wide = useMediaQuery(WIDE);
  return (
    <div className={wide ? "grid grid-cols-[1.15fr_1fr] items-stretch" : undefined}>
      {wide && <AuthHero page={page} />}
      <div className={wide ? "flex items-center justify-center p-10" : undefined}>
        <div className="mx-auto w-full max-w-sm">
          <AuthPanel mode={mode} routing={routing} />
        </div>
      </div>
    </div>
  );
}
