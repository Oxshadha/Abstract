/**
 * Passage markers become numbered references matching the citation chips:
 * "[S3]" -> "[3]", and grouped "[S1, S2]" (as Gemini writes them while streaming) -> "[1, 2]".
 */
export function withMarkers(text: string): string {
  return text
    .replace(/\[(S\d{1,2}(?:\s*(?:,|;|and)\s*S\d{1,2})+)\]/g, (_, group: string) =>
      ` [${(group.match(/\d{1,2}/g) ?? []).join(", ")}]`,
    )
    .replace(/\[S(\d{1,2})\]/g, " [$1]")
    .replace(/ {2,}\[/g, " [");
}
