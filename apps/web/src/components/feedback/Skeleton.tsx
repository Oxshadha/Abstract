/** Loading placeholders (spec 003 AC14). Pulse respects reduced motion; hidden from readers. */
function Bar({ className }: { className: string }) {
  return <div aria-hidden className={`rounded-sm bg-muted motion-safe:animate-pulse ${className}`} />;
}

export function ListRowSkeleton() {
  return (
    <div className="flex items-center gap-4 rounded-lg border border-border bg-surface p-4">
      <Bar className="size-10" />
      <div className="flex flex-1 flex-col gap-2">
        <Bar className="h-4 w-2/3" />
        <Bar className="h-3 w-1/3" />
      </div>
    </div>
  );
}

export function SummaryCardSkeleton() {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4">
      <Bar className="h-5 w-1/3" />
      <Bar className="h-3 w-full" />
      <Bar className="h-3 w-5/6" />
      <Bar className="h-3 w-2/3" />
    </div>
  );
}

export function ChatMessageSkeleton() {
  return (
    <div className="flex gap-3">
      <Bar className="size-8 rounded-pill" />
      <div className="flex flex-1 flex-col gap-2">
        <Bar className="h-3 w-full" />
        <Bar className="h-3 w-3/4" />
      </div>
    </div>
  );
}

/** Wraps skeletons so assistive technology hears one "Loading" announcement. */
export function Loading({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div role="status" aria-label={label} aria-busy="true" className="flex flex-col gap-3">
      {children}
    </div>
  );
}
