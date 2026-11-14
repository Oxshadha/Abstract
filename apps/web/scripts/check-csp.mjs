// Spec 017 AC2: the production CSP (infra/nginx/abstract.conf) allows inline scripts only by
// hash. If the theme script in a page shell changes, its hash must change in nginx too, or the
// browser blocks it in production. CI runs this (pnpm check:csp) so that never reaches a deploy.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../..", import.meta.url));
const nginx = readFileSync(`${root}infra/nginx/abstract.conf`, "utf8");
const problems = [];

const enforcing = nginx.match(/add_header Content-Security-Policy "/g) ?? [];
if (enforcing.length < 3) problems.push(`expected an enforcing CSP in every page location, found ${enforcing.length}`);
if (nginx.includes("Content-Security-Policy-Report-Only")) problems.push("the CSP is still report-only");

const policy = /Content-Security-Policy "([^"]+)"/.exec(nginx)?.[1] ?? "";
if (policy.includes("unsafe-eval")) problems.push("the CSP allows unsafe-eval");
if (/script-src[^;]*'unsafe-inline'/.test(policy)) problems.push("script-src allows all inline scripts");
for (const directive of ["frame-ancestors 'none'", "object-src 'none'", "base-uri 'self'"]) {
  if (!policy.includes(directive)) problems.push(`the CSP is missing ${directive}`);
}

for (const page of ["index.html", "landing.html"]) {
  const html = readFileSync(`${root}apps/web/${page}`, "utf8");
  for (const [, body] of html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)) {
    const hash = `'sha256-${createHash("sha256").update(body).digest("base64")}'`;
    if (!nginx.includes(hash)) problems.push(`${page}: inline script ${hash} is not allowed by the CSP`);
  }
}

if (problems.length) {
  console.error(problems.map((p) => `CSP: ${p}`).join("\n"));
  process.exit(1);
}
console.log("CSP: enforcing in every location; inline scripts allowed by hash only");
