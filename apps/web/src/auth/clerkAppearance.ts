import { darkColors, fonts, lightColors, radius } from "@/styles/tokens";

/** Clerk appearance from design tokens (spec 003 AC8, D43). Clerk needs literal values. */
export function clerkAppearance(theme: "light" | "dark") {
  const c = theme === "dark" ? darkColors : lightColors;
  return {
    // "Continue with Google" (and any other provider enabled in Clerk) as a full-width button
    // above the email form.
    layout: { socialButtonsPlacement: "top" as const, socialButtonsVariant: "blockButton" as const },
    // Every colour Clerk draws with, from our tokens; leaving one out lets Clerk derive it, which
    // gave dark text on the dark Continue button and an unreadable Google button.
    variables: {
      colorPrimary: c.primary,
      colorPrimaryForeground: c["primary-text"],
      colorBackground: c.surface,
      colorForeground: c.text,
      colorMuted: c.muted,
      colorMutedForeground: c["text-secondary"],
      colorNeutral: c.text,
      colorDanger: c.error,
      colorSuccess: c.success,
      colorWarning: c.warning,
      colorInput: c.surface,
      colorInputForeground: c.text,
      colorBorder: c.border,
      colorRing: c.focus,
      colorShadow: c.text,
      fontFamily: fonts.ui,
      borderRadius: radius.md,
    },
    // Flat monochrome buttons like the rest of the app (no Clerk gradient).
    elements: {
      // Our card is the card: Clerk's own box goes flat and full width, so there is no card
      // inside a card on desktop and nothing spills past the edge on phones (D96).
      rootBox: { width: "100%" },
      cardBox: { width: "100%", maxWidth: "100%", boxShadow: "none", border: "none", borderRadius: 0 },
      card: { boxShadow: "none", border: "none", backgroundColor: "transparent", paddingLeft: 0, paddingRight: 0 },
      footer: { background: "transparent" },
      // Clerk draws borders as box-shadow rings and ignores `border`, so outlines use a ring too.
      formButtonPrimary: { backgroundImage: "none", boxShadow: "none" },
      // White on a white card was invisible: a strong ring and the muted fill make it a button.
      socialButtonsBlockButton: { boxShadow: `0 0 0 1px ${c["border-strong"]}`, backgroundColor: c.muted },
      socialButtonsBlockButtonText: { color: c.text, fontWeight: 500 },
      // Inputs get their ring from index.css: Clerk's internal input rule outranks this object.
      otpCodeFieldInput: { boxShadow: `0 0 0 1px ${c["border-strong"]}` },
    },
  };
}

export function currentTheme(): "light" | "dark" {
  const explicit = document.documentElement.dataset.theme;
  if (explicit === "light" || explicit === "dark") return explicit;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
