// Spec 016 (D94): the How it works demo is a real recording of the Workspace, not an animation.
// Run against the local stack (development login) with the Attention paper in the demo library:
//   node scripts/landing-video.mjs <paperId> <outDir>
// Writes demo-raw.webm and demo-cut.json (the seconds to keep); scripts/landing-video.sh turns
// them into public/landing/demo.mp4, demo.webm and the poster.
import { mkdirSync, readdirSync, renameSync, writeFileSync } from "node:fs";

import { chromium } from "@playwright/test";

const [paperId, out = "public/landing"] = process.argv.slice(2);
if (!paperId) {
  console.error("Usage: node scripts/landing-video.mjs <paperId> [outDir]");
  process.exit(2);
}
const base = process.env.BASE_URL ?? "http://localhost:5173";
const size = { width: 1440, height: 900 };
const raw = `${out}/.video`;
mkdirSync(raw, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: size, recordVideo: { dir: raw, size } });
const t0 = Date.now();
const at = () => (Date.now() - t0) / 1000;
const page = await context.newPage();
await page.addInitScript(() => {
  localStorage.setItem("abstract.theme", "light");
  localStorage.setItem("abstract.tip.selection", "1");
});
await page.goto(`${base}/app/papers/${paperId}`);
const demo = page.getByRole("button", { name: /continue as demo user/i });
await demo.waitFor({ timeout: 15_000 }).then(() => demo.click()).catch(() => undefined);
await page.getByText("Research Problem").first().waitFor({ timeout: 60_000 });
const ask = page.getByRole("button", { name: "Ask Abstract" });
if ((await ask.getAttribute("aria-pressed")) !== "true") await ask.click();
await page.locator(".textLayer span").first().waitFor({ timeout: 60_000 });

// A fresh conversation, so the chat shows only this demo's question.
await page.getByRole("region", { name: "Ask Abstract" }).locator('button[aria-haspopup="listbox"]').first().click();
await page.getByRole("button", { name: "New conversation" }).click();
await page.getByLabel("Ask about this paper").waitFor();
// Start the paper at its title (arXiv's copy prints a permission notice above it). The viewer
// re-anchors while panels settle, so scroll until the title stays at the top.
const toTitle = () =>
  page.evaluate(() => {
    const scroller = document.querySelector('[aria-label="Paper pages"]');
    const title = [...document.querySelectorAll(".textLayer span")].find((s) => s.textContent?.trim() === "Attention Is All You Need");
    if (!scroller || !title) return 999;
    const offset = title.getBoundingClientRect().top - scroller.getBoundingClientRect().top - 16;
    scroller.scrollTop += offset;
    return Math.abs(offset);
  });
for (let i = 0; i < 6; i++) {
  await page.waitForTimeout(800);
  if ((await toTitle()) < 4 && i > 1) break;
}
await page.mouse.move(700, 500);
await page.waitForTimeout(1200);
console.log("title offset before recording:", await toTitle());
const start = at();

// 1. Ask a question; the answer streams with numbered sources.
const input = page.getByLabel("Ask about this paper");
await input.click();
await page.keyboard.type("What BLEU score does the big model reach?", { delay: 55 });
await page.waitForTimeout(400);
await page.keyboard.press("Enter");
const answers = page.getByRole("button", { name: /^\[1\]/ });
await answers.first().waitFor({ timeout: 60_000 });
await page.waitForTimeout(2000);

// 2. A source opens the paper there: a table is outlined, a sentence highlighted.
const table = page.getByRole("button", { name: /Table \d+, p\. \d+/ }).first();
const target = (await table.count()) > 0 ? table : answers.first();
await target.scrollIntoViewIfNeeded();
await target.hover();
await page.waitForTimeout(500);
await target.click();
await page.waitForTimeout(3200);
const end = at();

await context.close();
await browser.close();
const [video] = readdirSync(raw).filter((f) => f.endsWith(".webm"));
renameSync(`${raw}/${video}`, `${out}/demo-raw.webm`);
writeFileSync(`${out}/demo-cut.json`, JSON.stringify({ start, end }));
console.log(`Recorded ${(end - start).toFixed(1)} s of demo (from ${start.toFixed(1)} s) into ${out}/demo-raw.webm`);
