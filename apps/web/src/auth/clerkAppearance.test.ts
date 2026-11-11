import { describe, expect, it } from "vitest";

import { darkColors, fonts, lightColors } from "@/styles/tokens";

import { clerkAppearance } from "./clerkAppearance";

describe("AC8: Clerk appearance comes from design tokens", () => {
  it.each([
    ["light", lightColors],
    ["dark", darkColors],
  ] as const)("%s theme", (theme, colors) => {
    const { variables } = clerkAppearance(theme);
    expect(variables.colorPrimary).toBe(colors.primary);
    expect(variables.colorBackground).toBe(colors.surface);
    expect(variables.colorForeground).toBe(colors.text);
    expect(variables.fontFamily).toBe(fonts.ui);
  });
});
