/** Abstract. logo (UI/LOGO). Colours come from tokens, so it follows the theme. */
export function LogoMark({ className = "size-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden>
      <path
        d="M20.5 9.5 49 6.5c4-.4 6.7 2.1 6.3 6.3L52.5 44c-.3 3.2-2.6 5.5-5.8 5.9l-29 3c-4.2.4-6.8-2.1-6.4-6.2l2.8-31.3c.3-3.1 2.6-5.5 6.4-5.9Z"
        fill="var(--color-logo-back)"
      />
      <path
        d="M14.7 16.3 39 14.1c3.9-.4 6.5 2.1 6.1 6l-2.7 32.1c-.3 3.9-2.6 6-6.4 5.6L11.7 55.6c-3.9-.4-6.1-2.9-5.7-6.7l2.7-26.7c.3-3.4 2.4-5.5 6-5.9Z"
        fill="var(--color-logo-front)"
      />
    </svg>
  );
}

export function Logo() {
  return (
    <span className="inline-flex items-center gap-2">
      <LogoMark />
      <span className="font-display text-2xl font-bold tracking-tight">abstract.</span>
    </span>
  );
}
