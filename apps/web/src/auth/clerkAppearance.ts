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
      formButtonPrimary: { backgroundImage: "none", boxShadow: "none" },
      socialButtonsBlockButton: { boxShadow: "none", border: `1px solid ${c.border}` },
      formFieldInput: { border: `1px solid ${c["border-strong"]}`, boxShadow: "none" },
      otpCodeFieldInput: { border: `1px solid ${c["border-strong"]}` },
    },
  };
}

export function currentTheme(): "light" | "dark" {
  const explicit = document.documentElement.dataset.theme;
  if (explicit === "light" || explicit === "dark") return explicit;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
