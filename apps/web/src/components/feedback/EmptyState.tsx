import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** Empty state: icon, title, description and at most one action (spec 003 AC14). */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border-strong px-6 py-12 text-center">
      <Icon aria-hidden className="size-10 text-text-secondary" />
      <h2 className="font-display text-xl font-bold">{title}</h2>
      <p className="max-w-md text-text-secondary">{description}</p>
      {action}
    </div>
  );
}
