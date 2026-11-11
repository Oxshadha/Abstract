import { expect, test, type Page } from "@playwright/test";

import { makePdf } from "./pdf";

/**
 * Happy path across specs 004 to 013: sign in (dev login), upload on Home, process, chat with a
 * citation, find the paper in the Library, file it in a new collection, then search inside that
 * collection and open a passage at its page.
 */

async function signIn(page: Page) {
  await page.goto("/app");
  const demo = page.getByRole("button", { name: /continue as demo user/i });
  if (await demo.isVisible().catch(() => false)) await demo.click();
  await expect(page.getByRole("heading", { level: 1, name: "Home" })).toBeVisible({ timeout: 15_000 }); // first compile of a cold dev server
}

test("upload a paper and open it once chat is available", async ({ page }, testInfo) => {
  const title = `Attention Study ${String(Date.now())} ${testInfo.project.name}`;
  const pdf = makePdf(title);
  await signIn(page);
  await page.screenshot({ path: testInfo.outputPath("home.png"), fullPage: true });

  await page.locator('input[type="file"]').setInputFiles({ name: "study.pdf", mimeType: "application/pdf", buffer: pdf });

  // Step 02 (spec 006): Quick Summary is preselected; Continue starts it.
  await expect(page).toHaveURL(/\/app\/papers\/[0-9a-f-]+\/template$/);
  await expect(page.getByRole("radio", { name: /Quick Summary/ })).toHaveAttribute("aria-checked", "true");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/app\/papers\/[0-9a-f-]+\/processing$/);
  await expect(page.getByRole("heading", { name: "Processing your paper" })).toBeVisible();
  await expect(page.getByText("Extracting text", { exact: true })).toBeVisible({ timeout: 15_000 });
  const open = page.getByRole("link", { name: "Open workspace" });
  await expect(open).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: testInfo.outputPath("processing-done.png"), fullPage: true });

  // Spec 007: ask a question in the workspace and get a cited answer.
  await open.click();
  await expect(page).toHaveURL(/\/app\/papers\/[0-9a-f-]+$/);
  const paperId = new URL(page.url()).pathname.split("/").pop() ?? "";
  if (testInfo.project.use.isMobile) await page.getByRole("button", { name: "Chat" }).click();
  else await page.getByRole("button", { name: "Ask Abstract" }).click(); // desktop toolbar
  const input = page.getByLabel("Ask about this paper");
  await expect(input).toBeEnabled({ timeout: 30_000 });
  await input.fill("What does self attention relate?");
  await input.press("Enter");
  await expect(page.getByRole("button", { name: /^\[1\] p\. 1/ }).first()).toBeVisible({ timeout: 45_000 });
  await page.screenshot({ path: testInfo.outputPath("chat-answer.png"), fullPage: true });

  // Spec 008 AC4: the chip opens the paper at the cited page and marks the sentence.
  await page.getByRole("button", { name: /^\[1\] p\. 1/ }).first().click();
  await expect(page.locator('mark[data-citation="true"]').first()).toBeVisible({ timeout: 20_000 });
  // Opening a citation must not disturb the conversation (phones switch tabs, D60).
  await expect(page.locator('mark[data-citation="true"]').first()).toBeVisible();
  if (testInfo.project.use.isMobile) await page.getByRole("button", { name: "Chat" }).click();
  await expect(page.getByRole("button", { name: /^\[1\] p\. 1/ }).first()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("citation-highlight.png"), fullPage: true });

  await page.getByRole("link", { name: "Library" }).first().click();
  // By id: the summary may tidy the displayed title (it is model output).
  const row = page.getByRole("listitem").filter({ has: page.locator(`a[href$="/app/papers/${paperId}"]`) });
  await expect(row.getByText("Ready")).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: testInfo.outputPath("library-after.png"), fullPage: true });

  // No horizontal scroll at any width (D60).
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);

  // Spec 013 AC7: file the paper in a new collection from its menu.
  const folder = `E2E ${String(Date.now())}`;
  await row.getByRole("button", { name: /^Actions for/ }).click();
  await page.getByRole("menuitem", { name: "Add to collection" }).click();
  await page.getByPlaceholder("New collection").fill(folder);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("checkbox", { name: new RegExp(folder) })).toHaveAttribute("aria-checked", "true");
  await page.getByRole("button", { name: "Done" }).click();
  if (testInfo.project.use.isMobile) await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: new RegExp(folder) }).click();
  await expect(page.getByRole("heading", { level: 1, name: folder })).toBeVisible();
  await expect(page.getByRole("listitem").filter({ has: page.locator(`a[href$="/app/papers/${paperId}"]`) })).toBeVisible();

  // Spec 013 AC8: search inside the open collection and open the passage at its page.
  if (testInfo.project.use.isMobile) await page.getByRole("button", { name: "Search", exact: true }).click();
  else await page.keyboard.press("ControlOrMeta+k");
  await page.getByRole("combobox", { name: "Search papers" }).fill("relates positions");
  const passage = page.getByRole("option").filter({ hasText: "p. 1" }).first();
  await expect(passage).toBeVisible({ timeout: 10_000 });
  await page.screenshot({ path: testInfo.outputPath("search.png"), fullPage: true });
  await passage.click();
  await expect(page).toHaveURL(new RegExp(`/app/papers/${paperId}$`));
  await expect(page.locator('mark[data-citation="true"]').first()).toBeVisible({ timeout: 20_000 });
});
