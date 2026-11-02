/** The user's local date. `toISOString` would give the UTC date, which can be a day off. */
export function localToday(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

export function formatMoney(amount: number, currency = "USD"): string {
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(amount);
}

/** An amount as typed: `null` when empty, `NaN` when it isn't a number. */
export function parseAmount(text: string): number | null {
  const cleaned = text.replace(/[$,\s]/g, "");
  if (!cleaned) return null;
  return /^-?\d*\.?\d+$|^-?\d+\.$/.test(cleaned) ? Number(cleaned) : NaN;
}
