/** "about 40 seconds left", "about 2 minutes left"; never a range with a dash. */
export function timeLeft(seconds: number): string {
  if (seconds < 10) return "almost done"; // never promise seconds the parse may not keep
  if (seconds < 60) return `about ${String(Math.round(seconds / 5) * 5)} seconds left`;
  const minutes = Math.ceil(seconds / 60);
  return minutes === 1 ? "about 1 minute left" : `about ${String(minutes)} minutes left`;
}
