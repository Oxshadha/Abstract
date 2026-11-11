/**
 * Theme preference (spec 003 AC3): System, Light or Dark, stored per device.
 * "system" removes data-theme so tokens.css follows prefers-color-scheme.
 * The same logic runs inline in index.html before first paint (no flash of the wrong theme).
 */
export type ThemeChoice = "system" | "light" | "dark";
export const THEME_KEY = "abstract.theme";

export function readTheme(): ThemeChoice {
  try {
    const value = window.localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system"; // storage blocked (private mode, policy): follow the system
  }
}

export function applyTheme(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === "system") delete root.dataset.theme;
  else root.dataset.theme = choice;
  try {
    if (choice === "system") window.localStorage.removeItem(THEME_KEY);
    else window.localStorage.setItem(THEME_KEY, choice);
  } catch {
    // Not persisted when storage is unavailable; the choice still applies for this visit.
  }
}
