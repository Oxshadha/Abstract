import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import css from "../index.css?raw";
import html from "../../index.html?raw";

import { applyTheme, readTheme, THEME_KEY } from "./theme";
import { ThemeToggle } from "./ThemeToggle";

afterEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
  vi.restoreAllMocks();
});

describe("AC3: theme preference", () => {
  it("applies and persists light/dark, and system clears both", () => {
    applyTheme("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(readTheme()).toBe("dark");
    applyTheme("system");
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(window.localStorage.getItem(THEME_KEY)).toBeNull();
  });

  it("falls back to system when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    expect(readTheme()).toBe("system");
    expect(() => {
      applyTheme("dark");
    }).not.toThrow();
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("toggle is an accessible radio group", () => {
    render(<ThemeToggle />);
    const dark = screen.getByRole("radio", { name: "Dark" });
    fireEvent.click(dark);
    expect(dark).toHaveAttribute("aria-checked", "true");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("index.html applies the saved theme before first paint", () => {
    expect(html).toContain(`localStorage.getItem("${THEME_KEY}")`);
    expect(html.indexOf("abstract.theme")).toBeLessThan(html.indexOf("/src/main.tsx"));
  });
});

describe("AC4: self-hosted fonts", () => {
  it("never loads fonts from Google's CDN", () => {
    for (const text of [html, css]) {
      expect(text).not.toMatch(/fonts\.(googleapis|gstatic)\.com/);
    }
  });
});
