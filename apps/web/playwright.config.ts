import { defineConfig, devices } from "@playwright/test";

/**
 * One end-to-end happy path against the real local stack (`make dev`): web, API, worker,
 * Postgres, Redis and S3-compatible storage, with the fake LLM provider. Run: `make e2e`.
 */
export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,
  retries: 0,
  reporter: [["list"]],
  outputDir: "node_modules/.tmp/playwright",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
  },
  projects: [
    // Every mainstream engine: Chromium (Chrome, Edge), WebKit (Safari, every iPhone browser)
    // and Gecko (Firefox). pdf.js once broke in Safari only, unseen by a Chromium-only run.
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
    { name: "desktop-safari", use: { ...devices["Desktop Safari"] } },
    { name: "mobile-safari", use: { ...devices["iPhone 14"] } },
    { name: "desktop-firefox", use: { ...devices["Desktop Firefox"] } },
  ],
});
