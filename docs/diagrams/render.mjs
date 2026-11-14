// Renders the hand-drawn diagrams in docs/diagrams/*.html to PNG for the README.
//   cd apps/web && node ../../docs/diagrams/render.mjs
import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const here = fileURLToPath(new URL(".", import.meta.url));
const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: 2 });
for (const name of ["architecture", "pipeline"]) {
  await page.goto(`file://${here}${name}.html`);
  await page.waitForLoadState("networkidle");
  // Lucide icons (ISC licence) are inlined so they take the colour of their tile.
  const names = await page.$$eval("[data-icon]", (els) => els.map((e) => e.getAttribute("data-icon")));
  const svgs = Object.fromEntries(names.map((n) => [n, readFileSync(`${here}icons/lucide/${n}.svg`, "utf8").replace(/<!--.*?-->/s, "")]));
  await page.$$eval("[data-icon]", (els, map) => { for (const e of els) e.innerHTML = map[e.getAttribute("data-icon")]; }, svgs);
  await page.locator("#canvas").screenshot({ path: `${here}../images/${name}.png` });
  console.log("rendered", name);
}
await browser.close();
