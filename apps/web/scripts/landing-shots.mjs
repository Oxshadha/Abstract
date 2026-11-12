// Spec 016 (D93): the landing page's product image is a real screenshot of the Workspace.
// Run against the local stack with the Attention paper in the demo library:
//   node scripts/landing-shots.mjs <paperId> <outDir>
// Writes workspace-light.png and workspace-dark.png (1600 x 1000); convert with
// scripts/landing-images.py.
import { chromium } from "@playwright/test";

const [paperId, out = "public/landing"] = process.argv.slice(2);
if (!paperId) {
  console.error("Usage: node scripts/landing-shots.mjs <paperId> [outDir]");
  process.exit(2);
}
const base = process.env.BASE_URL ?? "http://localhost:5173";
const browser = await chromium.launch();
for (const theme of ["light", "dark"]) {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1 });
  await page.addInitScript((t) => {
    localStorage.setItem("abstract.theme", t);
    localStorage.setItem("abstract.tip.selection", "1"); // the one-time tip is not part of the product shot
  }, theme);
  await page.goto(`${base}/app/papers/${paperId}`);
  const demo = page.getByRole("button", { name: /continue as demo user/i });
  await demo.waitFor({ timeout: 15_000 }).then(() => demo.click()).catch(() => undefined);
  await page.getByText("Research Problem").first().waitFor({ timeout: 60_000 });
  const ask = page.getByRole("button", { name: "Ask Abstract" });
  if ((await ask.getAttribute("aria-pressed")) !== "true") await ask.click();
  await page.locator(".textLayer span").first().waitFor({ timeout: 60_000 });
  await page.getByRole("button", { name: /^\[1\]/ }).first().waitFor({ timeout: 90_000 });
  // Start the paper at its title: arXiv's copy prints a permission notice above it, which is
  // part of the PDF, not of Abstract, and only distracts in a product shot.
  await page.evaluate(() => {
    const scroller = document.querySelector('[aria-label="Paper pages"]');
    const title = [...document.querySelectorAll(".textLayer span")].find((s) => s.textContent?.trim() === "Attention Is All You Need");
    if (scroller && title) scroller.scrollTop += title.getBoundingClientRect().top - scroller.getBoundingClientRect().top - 16;
  });
  await page.waitForTimeout(1500);
  await page.mouse.move(0, 999);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${out}/workspace-${theme}.png` });
  await page.close();
}
await browser.close();
console.log(`Saved ${out}/workspace-light.png and workspace-dark.png`);
