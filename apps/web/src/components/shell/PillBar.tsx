import type { ReactNode } from "react";

export interface PillItem {
  key: string;
  label: string;
  icon: ReactNode;
  active: boolean;
  /** Either a link (rendered by the caller) or a button action. */
  render?: (props: { className: string; children: ReactNode; "aria-label": string; title: string }) => ReactNode;
  onSelect?: () => void;
}

const HIDE_FROM = { md: "md:hidden", lg: "lg:hidden" } as const;

// Three blur strengths, each masked to a band: light near the top of the area, strong at the edge.
const BLUR_LAYERS = [
  { className: "backdrop-blur-[2px]", mask: "linear-gradient(to top, black 0%, black 50%, transparent 100%)" },
  { className: "backdrop-blur-[6px]", mask: "linear-gradient(to top, black 0%, black 30%, transparent 70%)" },
  { className: "backdrop-blur-[14px]", mask: "linear-gradient(to top, black 0%, transparent 45%)" },
];

/**
 * Floating navigation pill for phones (D86): bottom of the screen within thumb reach, translucent
 * with a blur so the page scrolls underneath. Icons only (owner review); the active one is a
 * filled pill, and every item keeps its name for screen readers and the tooltip.
 */
export function PillBar({ label, items, hideFrom = "md" }: { label: string; items: PillItem[]; hideFrom?: keyof typeof HIDE_FROM }) {
  return (
    <nav
      aria-label={label}
      className={`pointer-events-none fixed inset-x-0 bottom-0 z-20 flex justify-center px-4 pt-2 pb-[max(0.75rem,env(safe-area-inset-bottom))] ${HIDE_FROM[hideFrom]}`}
    >
      {/* Progressive blur across the whole bottom edge (owner review, like iOS): strongest at the
          bottom, fading out upward, so content dissolves into the bar instead of being cut. */}
      <div aria-hidden className="absolute inset-x-0 bottom-0 h-32">
        {BLUR_LAYERS.map((layer) => (
          <div key={layer.className} className={`absolute inset-0 ${layer.className}`} style={{ maskImage: layer.mask, WebkitMaskImage: layer.mask }} />
        ))}
      </div>
      <ul className="pointer-events-auto relative flex items-center gap-1 rounded-pill border border-border bg-surface/85 p-1.5 shadow-overlay backdrop-blur-xl backdrop-saturate-150">
        {items.map((item) => {
          const className = `flex size-11 items-center justify-center rounded-pill px-0 transition-colors motion-reduce:transition-none ${
            item.active ? "bg-primary text-primary-text" : "text-text-secondary hover:text-text"
          }`;
          const children = item.icon;
          return (
            <li key={item.key}>
              {item.render ? (
                item.render({ className, children, "aria-label": item.label, title: item.label })
              ) : (
                <button type="button" aria-label={item.label} title={item.label} aria-pressed={item.active} onClick={item.onSelect} className={className}>
                  {children}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
