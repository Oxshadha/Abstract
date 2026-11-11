// Generates design tokens from design/tokens.json (spec 003 AC1, D43).
//   src/styles/tokens.css  CSS variables: base + light on :root, dark via [data-theme] or system
//   src/styles/theme.css   Tailwind v4 @theme mapping so utilities use tokens (bg-surface, ...)
//   src/styles/tokens.ts   typed values for places that need literals (e.g. Clerk appearance)
// Run with `make tokens` (or `pnpm tokens`). CI fails if the outputs are stale.
import { readFile, writeFile } from "node:fs/promises";

import StyleDictionary from "style-dictionary";

const SOURCE = new URL("../../../design/tokens.json", import.meta.url);
const OUT = new URL("../src/styles/", import.meta.url);
const HEADER = "Generated from design/tokens.json by scripts/build-tokens.mjs. Do not edit.";

async function resolve(tokens) {
  const sd = new StyleDictionary({
    tokens,
    log: { verbosity: "silent", warnings: "disabled" },
    platforms: { css: { transformGroup: "css", prefix: "abs" } },
  });
  const { allTokens } = await sd.getPlatformTokens("css");
  return allTokens.map((t) => ({
    name: t.name,
    path: t.path,
    type: t.$type ?? t.type,
    value: String(t.$value ?? t.value),
  }));
}

const block = (selector, tokens, indent = "  ") =>
  `${selector} {\n${tokens.map((t) => `${indent}--${t.name}: ${t.value};`).join("\n")}\n}`;

const source = JSON.parse(await readFile(SOURCE, "utf8"));
const base = await resolve(source.base);
const light = await resolve(source.light);
const dark = await resolve(source.dark);

const lightNames = light.map((t) => t.name).sort();
const darkNames = dark.map((t) => t.name).sort();
if (JSON.stringify(lightNames) !== JSON.stringify(darkNames)) {
  throw new Error("light and dark themes must define the same colour tokens");
}

const css = [
  `/* ${HEADER} */`,
  block(":root", [...base, ...light]),
  "",
  "/* Dark: explicit choice, or the system preference unless the user chose light. */",
  block('[data-theme="dark"]', dark),
  "@media (prefers-color-scheme: dark) {",
  block('  :root:not([data-theme="light"])', dark, "    "),
  "}",
  "",
].join("\n");

// Tailwind namespaces: --color-*, --font-*, --radius-*, --shadow-*, --spacing.
const themeName = (t) => {
  const [group, ...rest] = t.path;
  const key = rest.join("-");
  if (group === "spacing") return "spacing";
  return `${group}-${key}`;
};
const themeTokens = [...base, ...light];
const theme = [
  `/* ${HEADER} */`,
  "@theme inline {",
  ...themeTokens.map((t) => `  --${themeName(t)}: var(--${t.name});`),
  "}",
  "",
].join("\n");

const values = (list) =>
  Object.fromEntries(list.map((t) => [t.path.slice(1).join("-"), t.value]));
const ts = [
  `// ${HEADER}`,
  `export const fonts = ${JSON.stringify(values(base.filter((t) => t.path[0] === "font")), null, 2)} as const;`,
  `export const radius = ${JSON.stringify(values(base.filter((t) => t.path[0] === "radius")), null, 2)} as const;`,
  `export const lightColors = ${JSON.stringify(values(light), null, 2)} as const;`,
  `export const darkColors = ${JSON.stringify(values(dark), null, 2)} as const;`,
  "",
].join("\n");

await writeFile(new URL("tokens.css", OUT), css);
await writeFile(new URL("theme.css", OUT), theme);
await writeFile(new URL("tokens.ts", OUT), ts);
console.log(`tokens: ${base.length + light.length} base/light, ${dark.length} dark`);
