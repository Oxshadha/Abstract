# 003 — Design system: tokens, fonts, app shell, auth modal

| | |
|---|---|
| **Status** | Implemented (2026-11-11, PR pending CI). Sentry live (EU); source-map upload activates when the auth token is added |
| **Week** | W2 |
| **Decisions** | D17, D27, D33, D34, D35, D42, D43, D44, D45, D60, D62, D66, D67 |
| **Requirements** | R4, N7 |
| **Engineering practices (D67)** | All 8 items of `engineering-practices.md` §3 Spec 003 are included (AC9 to AC15) |
| **Feature flag** | none (core) |
| **Mockups** | `UI/Abstract Research Library Dashboard.png` (shell, sidebar, top bar), `UI/Abstract Research Login Dashboard-3.png` and `...Signup Interface-4.png` (auth), `UI/LOGO/*` |

## Goal
Every later screen is built from one visual system that matches the mockups: tokens defined once, fonts self-hosted, light and dark themes, a responsive shell (sidebar on desktop, drawer on mobile), and sign-in as a modal over the blurred app. Plus the frontend performance and resilience baseline, so every feature inherits it.

## Scope
**In:** `design/tokens.json` → Style Dictionary → `tokens.css` + `tokens.ts` · Tailwind v4 theme from tokens · shadcn/ui primitives restyled by tokens · self-hosted fonts · theme (system, light, dark) · Lucide icons · app shell (sidebar, top bar with ⌘K placeholder, user menu, mobile drawer) · route skeletons for Library, Collections, Templates, Settings, Workspace · auth modal + `/sign-in`, `/sign-up` fallback routes · Clerk appearance from tokens · query defaults, error boundaries, code splitting and bundle budget, Sentry and web-vitals, skeleton and empty states, offline banner, axe checks.
**Out:** page content (Library 013, Workspace 006 to 009, Templates 010, Admin 011) · landing page (016).

## Acceptance criteria
**Tokens and theming**
- [x] **AC1** — `design/tokens.json` is the single source for colours (D34 palette incl. WCAG-checked values), fonts, radius, spacing, shadows. `make tokens` generates `apps/web/src/styles/tokens.css` (light under `:root`, dark under `[data-theme="dark"]` and `prefers-color-scheme`) and `tokens.ts`; CI fails if generated files are stale.
- [x] **AC2** — No raw colour values or font names in components: a lint check fails on hex/rgb/hsl literals and font-family strings in `src/` outside the generated token files.
- [x] **AC3** — Theme toggle (System, Light, Dark) persists per device (localStorage, guarded) and applies before first paint (no flash of the wrong theme).
- [x] **AC4** — Fonts self-hosted via Fontsource (Google Sans Flex = headings, Google Sans = UI, Nunito Sans = reading text, D42) with `font-display: swap` and Latin subsets; no request to Google Fonts. If Google Sans is unavailable under its licence at build time, Google Sans Flex is used for UI and the fallback is recorded (assumption D3).
- [x] **AC5** — Colour discipline (D44) and UI text rules (D62): semantic colours only via status components (`StatusPill`, `Toast`, form error, citation highlight); the existing CI check rejects em/en dashes and emojis; icons are Lucide with `aria-label` or `aria-hidden`.

**Shell and navigation (mockups)**
- [x] **AC6** — App shell matches the Library mockup: left sidebar (logo, Library, Collections, Templates, Settings, Recent), top bar (search field placeholder with ⌘K hint, notifications placeholder, user avatar menu with theme and sign out). At < 768 px the sidebar becomes a slide-over drawer opened from a menu button; no horizontal scroll from 360 px; touch targets ≥ 44 px (D60).
- [x] **AC7** — Routes exist with skeleton content: `/app/library`, `/app/collections`, `/app/templates`, `/app/settings`, `/app/papers/$paperId` (Workspace shell with three panels on desktop, tabs on mobile, D60). Unknown routes show a friendly not-found page.
- [x] **AC8** — Auth (D45): signed-out users opening any `/app/*` route see the blurred app shell with a Clerk sign-in **modal**; `/sign-in` and `/sign-up` fallback routes use the split-screen mockup layout; with the dev login (D70) the modal is replaced by a "Continue as demo user" panel. Clerk's `appearance` uses the token values and fonts.

**Performance and resilience (practices §3 Spec 003)**
- [x] **AC9** — `QueryClient` defaults: `staleTime` 30 s, no retry on 4xx, at most 2 retries with backoff on network/5xx, `refetchOnWindowFocus` only where opted in (job status).
- [x] **AC10** — Workspace, Template builder and Admin routes are lazy-loaded; pdf.js, KaTeX, dnd-kit and the Clerk UI are not in the entry chunk. CI fails if the entry JS exceeds **200 KB gzip**.
- [x] **AC11** — Each Workspace panel and each route has an error boundary with a "Try again" action that reports to Sentry; the root has a fallback page.
- [x] **AC12** — `@sentry/react` initialised with release and environment (disabled when no DSN); source maps uploaded in CI and not served publicly.
- [x] **AC13** — `web-vitals` reports LCP, INP and CLS (to Sentry when configured); targets at p75: LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1.
- [x] **AC14** — Skeleton components for list rows, summary cards and chat messages; empty-state component with icon, title, description and one action; an offline banner appears when the browser goes offline and mutations are disabled until reconnect.
- [x] **AC15** — Vitest runs an axe accessibility check on every top-level screen and the auth modal; zero serious or critical violations; visible focus rings from tokens.

## Data / API
None new. Uses `GET /me` for the user menu.

## Edge cases & failure modes
- Clerk script fails to load (network, blocker): show the fallback `/sign-in` link and a calm error; the dev login is unaffected.
- localStorage blocked (private mode): theme falls back to System without errors.
- Reduced motion: drawer and modal transitions respect `prefers-reduced-motion`.
- Very long user or workspace names truncate with a tooltip.

## Latency / cost budget
Entry JS ≤ 200 KB gzip; LCP ≤ 2.5 s p75 on the Library route; fonts preloaded for the first view only.

## Test plan
Unit and component tests (Vitest + RTL) for theme, shell responsiveness (viewport mocks), auth gating, error boundaries, offline banner; axe checks; CI checks for stale tokens, raw colours and bundle size.

## Open questions (owner)
- **Q1 (answered):** Sentry now. Wired for web and API, disabled until the owner provides DSNs.
- **Q2 (answered):** `/app/papers/$paperId` confirmed; landing page at `/` (spec 016).
