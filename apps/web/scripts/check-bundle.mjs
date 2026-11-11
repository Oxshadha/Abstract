// Fails if the entry JavaScript exceeds the gzip budget (spec 003 AC10). Run after `pnpm build`.
import { readdirSync, readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";

const BUDGET_KB = 200;
const html = readFileSync(new URL("../dist/index.html", import.meta.url), "utf8");
const entry = /<script[^>]+src="\/(assets\/[^"]+\.js)"/.exec(html)?.[1];
if (!entry) throw new Error("entry script not found in dist/index.html (run pnpm build first)");

const sizeKb = (file) =>
  gzipSync(readFileSync(new URL(`../dist/${file}`, import.meta.url))).length / 1024;
const entryKb = sizeKb(entry);
const chunks = readdirSync(new URL("../dist/assets", import.meta.url)).filter((f) => f.endsWith(".js"));
console.log(`entry ${entry}: ${entryKb.toFixed(1)} KB gzip (budget ${BUDGET_KB} KB), ${chunks.length} JS chunks`);
if (entryKb > BUDGET_KB) {
  console.error("Entry bundle over budget: lazy-load heavy dependencies (see spec 003 AC10).");
  process.exit(1);
}
