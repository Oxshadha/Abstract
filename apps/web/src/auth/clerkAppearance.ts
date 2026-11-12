import { darkColors, fonts, lightColors, radius } from "@/styles/tokens";

/** Clerk appearance from design tokens (spec 003 AC8, D43). Clerk needs literal values. */
export function clerkAppearance(theme: "light" | "dark") {
  const c = theme === "dark" ? darkColors : lightColors;
  return {
    // "Continue with Google" (and any other provider enabled in Clerk) as a full-width button
    // above the email form.
    layout: { socialButtonsPlacement: "top" as const, socialButtonsVariant: "blockButton" as const },
    variables: {
      colorPrimary: c.primary,
      colorBackground: c.surface,
      colorForeground: c.text,
      colorMutedForeground: c["text-secondary"],
      colorDanger: c.error,
      colorInput: c.surface,
      colorBorder: c["border-strong"],
      fontFamily: fonts.ui,
      borderRadius: radius.md,
    },
  };
}

export function currentTheme(): "light" | "dark" {
  const explicit = document.documentElement.dataset.theme;
  if (explicit === "light" || explicit === "dark") return explicit;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
