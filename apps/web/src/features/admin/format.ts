export const money = (usd: number): string =>
  usd >= 100 ? `$${usd.toFixed(0)}` : usd >= 1 ? `$${usd.toFixed(2)}` : usd === 0 ? "$0" : `$${usd.toFixed(4)}`;

export const count = (n: number): string => new Intl.NumberFormat().format(n);

export function when(iso: string | null | undefined): string {
  if (!iso) return "Never";
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }).format(new Date(iso));
}
