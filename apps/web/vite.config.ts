/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import { sentryVitePlugin } from "@sentry/vite-plugin";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In docker-compose the API is reachable as http://api:8000; on the host as localhost.
const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

// Source maps upload to Sentry only when CI provides SENTRY_AUTH_TOKEN (spec 003 AC12);
// maps are "hidden" (not referenced from the bundle) and deleted after upload.
const sentryUpload = process.env.SENTRY_AUTH_TOKEN
  ? [
      sentryVitePlugin({
        org: process.env.SENTRY_ORG,
        project: process.env.SENTRY_PROJECT_WEB,
        authToken: process.env.SENTRY_AUTH_TOKEN,
        sourcemaps: { filesToDeleteAfterUpload: ["./dist/**/*.map"] },
      }),
    ]
  : [];

export default defineConfig({
  // One .env at the repo root; only VITE_-prefixed values reach the browser.
  envDir: "../..",
  build: { sourcemap: "hidden" },
  plugins: [react(), tailwindcss(), ...sentryUpload],
  resolve: {
    alias: [
      { find: "@", replacement: fileURLToPath(new URL("./src", import.meta.url)) },
      // pdf.js 6's modern build calls APIs newer than Safari 18 and older Chrome
      // (Map.prototype.getOrInsertComputed, Math.sumPrecise); the legacy build polyfills them.
      // Exact match only, so react-pdf's `import "pdfjs-dist"` gets it too.
      { find: /^pdfjs-dist$/, replacement: "pdfjs-dist/legacy/build/pdf.mjs" },
    ],
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": { target: apiTarget, changeOrigin: true } },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"], // e2e/ runs with Playwright against the real stack
    css: false,
  },
});
