import { expect, test, type Page } from "@playwright/test";

import { makePdf } from "./pdf";

/** Spec 004 happy path: sign in (dev login), upload a PDF, watch it process, find it ready. */

async function signIn(page: Page) {
  await page.goto("/app/library");
  const demo = page.getByRole("button", { name: /continue as demo user/i });
  if (await demo.isVisible().catch(() => false)) await demo.click();
  await expect(page.getByRole("heading", { name: "Your Library" })).toBeVisible();
}

test("upload a paper and open it once chat is available", async ({ page }, testInfo) => {
  const title = `Attention Study ${String(Date.now())} ${testInfo.project.name}`;
  const pdf = makePdf(title);
  await signIn(page);
  await page.screenshot({ path: testInfo.outputPath("library.png"), fullPage: true });

  await page.locator('input[type="file"]').setInputFiles({ name: "study.pdf", mimeType: "application/pdf", buffer: pdf });

  // Step 02 (spec 006): Quick Summary is preselected; Continue starts it.
  await expect(page).toHaveURL(/\/app\/papers\/[0-9a-f-]+\/template$/);
  await expect(page.getByRole("radio", { name: /Quick Summary/ })).toHaveAttribute("aria-checked", "true");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/app\/papers\/[0-9a-f-]+\/processing$/);
  await expect(page.getByRole("heading", { name: "Processing your paper" })).toBeVisible();
  await expect(page.getByText("Extracting text", { exact: true })).toBeVisible();
  const open = page.getByRole("link", { name: "Open workspace" });
  await expect(open).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: testInfo.outputPath("processing-done.png"), fullPage: true });

  await page.getByRole("link", { name: "Library" }).first().click();
  const row = page.getByRole("listitem").filter({ hasText: title });
  await expect(row.getByText("Ready")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("library-after.png"), fullPage: true });

  // No horizontal scroll at any width (D60).
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
