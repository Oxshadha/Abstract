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

describe("D96: the Google button stands out from the card", () => {
  it.each([
    ["light", lightColors],
    ["dark", darkColors],
  ] as const)("%s theme", (theme, colors) => {
    const button = clerkAppearance(theme).elements.socialButtonsBlockButton;
    expect(button.boxShadow).toBe(`0 0 0 1px ${colors["border-strong"]}`);
    expect(button.backgroundColor).not.toBe(colors.surface);
  });
});

describe("D96: Clerk's card never clips the fields", () => {
  it("fits its box exactly and lets edges and the Last used tag show", () => {
    const { cardBox, card } = clerkAppearance("light").elements;
    expect(cardBox.overflow).toBe("visible");
    expect(card.margin).toBe(0);
    expect(card.width).toBe("100%");
  });
});

describe("Production feedback: Clerk follows a theme change while open", () => {
  it("useCurrentTheme updates when data-theme changes", async () => {
    const { renderHook, act } = await import("@testing-library/react");
    const { useCurrentTheme } = await import("./clerkAppearance");
    document.documentElement.dataset.theme = "light";
    const { result } = renderHook(() => useCurrentTheme());
    expect(result.current).toBe("light");
    await act(async () => {
      document.documentElement.dataset.theme = "dark";
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(result.current).toBe("dark");
    delete document.documentElement.dataset.theme;
  });
});
