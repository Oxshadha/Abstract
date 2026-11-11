/**
 * Accessibility guard for the palette (D34): every text/background pair meets WCAG AA in both
 * themes, computed from design/tokens.json via the generated tokens.ts, so a future palette
 * change cannot silently break contrast.
 */
import { describe, expect, it } from "vitest";

import { darkColors, lightColors } from "./tokens";

function luminance(hex: string): number {
  const channel = (i: number) => {
    const c = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2);
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

const themes = { light: lightColors, dark: darkColors };

describe.each(Object.entries(themes))("%s theme", (_name, c) => {
  it.each([
    ["text", "bg"],
    ["text", "surface"],
    ["text-secondary", "bg"],
    ["text-secondary", "surface"],
    ["primary-text", "primary"],
    ["success", "success-bg"],
    ["warning", "warning-bg"],
    ["error", "error-bg"],
    ["info", "info-bg"],
  ] as const)("%s on %s meets 4.5:1", (fg, bg) => {
    expect(contrast(c[fg], c[bg])).toBeGreaterThanOrEqual(4.5);
  });

  it("strong borders meet 3:1 for control boundaries (WCAG 1.4.11)", () => {
    expect(contrast(c["border-strong"], c.surface)).toBeGreaterThanOrEqual(3);
  });
});
