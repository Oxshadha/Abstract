// Spec 016 AC7: render the landing page to static HTML after `vite build`.
// dist/index.html becomes the prerendered landing page and the app's own shell moves to
// dist/app.html (hosting serves it for /app/*, /sign-in/* and /sign-up/*, spec 017).
import { readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const dist = `${root}dist`;
const { render } = await import(`${root}dist-ssr/entry-server.js`);

const site = (process.env.SITE_URL ?? "").replace(/\/$/, "");
const meta = site
  ? [
      `<link rel="canonical" href="${site}/" />`,
      `<meta property="og:url" content="${site}/" />`,
      `<meta property="og:image" content="${site}/landing/og.png" />`,
      `<meta name="twitter:image" content="${site}/landing/og.png" />`,
    ].join("\n    ")
  : "";

const template = readFileSync(`${dist}/landing.html`, "utf8");
const html = template.replace("<!--landing-->", render()).replace("<!--site-meta-->", meta);
renameSync(`${dist}/index.html`, `${dist}/app.html`);
writeFileSync(`${dist}/index.html`, html);
rmSync(`${dist}/landing.html`);

writeFileSync(`${dist}/robots.txt`, `User-agent: *\nAllow: /\nDisallow: /app/\n${site ? `Sitemap: ${site}/sitemap.xml\n` : ""}`);
if (site) {
  writeFileSync(
    `${dist}/sitemap.xml`,
    `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url><loc>${site}/</loc></url>\n</urlset>\n`,
  );
} else {
  console.warn("SITE_URL is not set: canonical link, og:url, og:image and sitemap.xml are left out.");
}
rmSync(`${root}dist-ssr`, { recursive: true, force: true });
console.log("Prerendered the landing page into dist/index.html; the app shell is dist/app.html.");
