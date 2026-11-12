# 016 — Landing page

| | |
|---|---|
| **Status** | Draft |
| **Week** | W4 |
| **Decisions** | D27, D39, D42, D86, D89 |
| **Engineering practices (D67)** | Spec 016 item in `docs/engineering-practices.md` §3, included below as AC6 |
| **Feature flag** | none (public page) |
| **Mockup** | `UI/AI Research Made Clear-1.png`, `UI/Abstract AI Research Companion Landing Page-2.png` |

## Goal
A visitor understands what Abstract does in a few seconds, sees the real product, and signs up or logs in. The page loads fast on a phone and can be found by search engines.

## Scope
**In:**
- the public page at `/`:
  - header;
  - hero with the product image;
  - how it works (three steps);
  - features (four cards);
  - plans (Q3);
  - a closing call to action;
  - footer;
- built to static HTML at build time, so it shows before any JavaScript runs;
- search metadata (title, description, Open Graph image);
- signed-in visitors get a way straight back into the app.

**Out:**
- payments;
- blog or resources pages;
- a demo video (Q4);
- other languages.

## Acceptance criteria
- [ ] **AC1** — **Header and hero.**
  - **Header:** the "abstract." mark, links to Features, How it works and Plans (on-page anchors), "Log in", and "Get started".
  - **Hero:** headline, one supporting sentence, "Get started" and "See how it works", and the product image (Q1, Q2).
  - **Phones:** the header collapses to the mark, "Log in" and "Get started"; the section links move into the page, with no drawer (design principle 9).
- [ ] **AC2** — **How it works:** three steps (Upload a paper, Summarize and analyze, Explore and ask) as in the mockup.
- [ ] **AC3** — **Features:**
  - **The cards:** Structured summaries, Understand figures, Custom templates and Stay organized, with icons from the icon set.
  - **The claims:** every one matches what the product does today.
- [ ] **AC4** — **Plans section and closing:** the plans section (Q3), a closing call to action and a footer.
- [ ] **AC5** — **Calls to action.**
  - **Destinations:** "Get started" opens sign-up; "Log in" opens sign-in.
  - **Signed-in visitors:** see "Open your library" instead of both.
  - **No requests:** the page makes no API calls for anonymous visitors.
- [ ] **AC6** — **Speed (engineering practices §3).**
  - **The target:** the page meets LCP ≤ 2.5 s on a mid-range phone profile in Lighthouse.
  - **Fonts:** self-hosted with `font-display: swap` (D42).
  - **The product image:** responsive, modern format, with width and height set (no layout shift).
- [ ] **AC7** — **Prerendering and search.**
  - **Prerendering:** `/` is prerendered to static HTML at build time and becomes interactive afterwards.
  - **In the HTML:** a title, meta description, canonical link, Open Graph and Twitter card tags, and an Open Graph image.
  - **Crawlers:** `robots.txt` and a `sitemap.xml` with `/`.
- [ ] **AC8** — **Quality bar.**
  - Light and dark themes (following the system).
  - WCAG 2.1 AA, with no serious axe violations.
  - Works from 360 px with no horizontal scroll and 44 px touch targets.
  - Desktop uses the width (design principle 6b).
  - No em or en dashes or emojis.
  - Tokens only.

## Technical approach
- **Build step:** a small build step (`vite build --ssr` for the landing entry, then a Node script) renders the landing component with React's `renderToString` into `dist/index.html`. It uses no new dependency.
- **The app:** keeps its own HTML shell, served for `/app/*`, `/sign-in/*` and `/sign-up/*`. Hosting rewrites are set up in spec 017.
- **Hydration:** the landing component hydrates on the client. It reads sign-in state only after hydrating, so the static HTML stays the same for everyone.
- **The product image:** a real screenshot of the Workspace (light and dark), made by a script from the running app with a sample paper, saved as WebP at two widths (Q2).

## Edge cases
- **JavaScript disabled:** the page reads fully, and the links work as plain links.
- **A slow network:** text appears first; the image has its size reserved.
- **Dark mode before hydration:** the inline theme script already sets it (spec 003), so there is no flash.

## Test plan
- **Unit:** the landing component renders every section and its links; the prerender output contains the headline and metadata.
- **Web:** signed-in visitors see "Open your library"; anonymous visitors make no API calls; axe.
- **Playwright:** the landing page at phone and desktop widths with no horizontal scroll; "Get started" reaches sign-up.
- **Lighthouse:** run against the production build (mobile profile), with the result recorded in the log.

## Open questions (owner)
- **Q1:** Which layout? The two mockups differ: a left-aligned hero ("Read, understand, and explore research papers.") with steps and feature cards, or a centred hero ("Research papers, made clear.").
- **Q2:** The product image: a real screenshot of the app, or a hand-built HTML picture of it?
- **Q3:** What does the plans section say while there are no payments?
- **Q4:** What does "See demo" or "See how it works" do?
