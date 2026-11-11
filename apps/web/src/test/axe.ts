import axe from "axe-core";

/**
 * Runs axe on a rendered tree and returns serious/critical violations (spec 003 AC15).
 * color-contrast is disabled because jsdom cannot compute styles; contrast is verified exactly
 * from the tokens instead (src/styles/tokens.test.ts).
 */
export async function seriousViolations(container: Element): Promise<string[]> {
  const result = await axe.run(container, {
    rules: { "color-contrast": { enabled: false } },
    resultTypes: ["violations"],
  });
  return result.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`);
}
