# Design principles

The owner's standing rules for every screen, collected from design reviews. Follow them without being asked; when a screen breaks one, fix it as part of the work. The tokens, fonts and colour rules in `AGENTS.md` still apply. Decisions: D44, D60, D79, D82, D83, D84, D86.

## Layout and density
1. **Phones first.** Design the 360 px layout first, then add for tablet and desktop. No horizontal scroll, touch targets at least 44 px.
2. **One clean line per item on phones.** A list row is: icon, title (with one short meta line under it), then actions as icons. Secondary columns (status pill, time column, Open button) appear from tablet width up.
3. **Say it once.** No subtitles or helper text that repeat what the screen already shows (a heading plus an upload box that explains itself is enough).
4. **Headers stay on one line.** Back, title (truncated, with type or authors beneath in small text), then actions. Never let a header wrap into stacked rows.
5. **The window never scrolls; areas do.** The app fills the window: the sidebar stays fixed (only its Collections list scrolls, without a visible scrollbar), page headers and toolbars stay put, and only the list, document or panel content scrolls. In the Workspace each panel scrolls on its own; the Summary heading and template switcher stay fixed.
6. **Fixed tools, scrolling content.** On phones the main tool of a screen (the upload box on Home, the composer in chat) stays put; only the list or content area scrolls, and it scrolls under the floating bars rather than stopping above them.
6b. **Desktop uses the width.** Pages fill the space beside the sidebar with the same side padding as Library and Templates; never a narrow column centred between empty margins. Short content goes into a grid of cards (two columns from desktop up) instead. Reading text keeps a comfortable line length inside its own card or panel, not by shrinking the page.

## Navigation
7. **Brand is always visible.** The "abstract." logo is at the top left on every screen size.
8. **Phones navigate with a floating pill at the bottom**, translucent with a blur so content shows through as it scrolls under it. Icons only; the current place is a filled pill. The Workspace uses the same pill for Paper, Summary and Chat.
9. **No hamburger drawers.** What lived in the sidebar gets a phone home of its own (collections are a chip row at the top of the Library).

## Controls
10. **Icons over words on phones** when the icon is clear (star, menu, theme, navigation). Every icon-only control keeps its name for screen readers and as a tooltip. Use text only where an icon would be ambiguous.
11. **No browser-default controls.** No native selects, number spinners or date pickers: use the shared `Select`, `Menu` and `Dialog`, so every browser and theme looks the same.
12. **One action, one place.** If an action has its own icon on the row (star), it does not repeat in the row's menu.
13. **Popups float.** Menus and dropdowns render above everything and are never clipped by a scrolling sidebar or panel; they stay inside the window and flip upward when needed.
14. **Destructive actions read as such.** Delete and Sign out are red (text and icon) in menus; confirmation dialogs keep neutral buttons.

## Colour and type
15. **Monochrome by default.** Status colours only in status pills or icons, form errors, toasts, the citation highlight and destructive menu items, and always through `components/status` (CI checks this).
16. **Tokens only.** No raw colours or font names; no em or en dashes and no emojis in UI text.

## Quality bar
17. **Check every browser for UI work.** UI and rendering changes are verified with Playwright in Chromium, WebKit and Firefox on desktop and phone sizes, and the phone screenshots are looked at, not just the test result. Run `scripts/check-ui-text.sh` before committing.
18. **Feels instant.** Optimistic updates with rollback, prefetch on hover, skeletons instead of spinners, debounced search.
