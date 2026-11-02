/** The user's local date. `toISOString` would give the UTC date, which can be a day off. */
export function localToday(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

export function formatMoney(amount: number): string {
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(amount);
}

/** An amount as typed: `null` when empty, `NaN` when it isn't a number. */
export function parseAmount(text: string): number | null {
  const cleaned = text.replace(/[$,\s]/g, "");
  if (!cleaned) return null;
  return /^-?\d*\.?\d+$|^-?\d+\.$/.test(cleaned) ? Number(cleaned) : NaN;
}

/** A YYYY-MM-DD date, without the time-zone shift `new Date(text)` would apply. */
export function formatDate(text: string): string {
  const [year, month, day] = text.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export const PAYMENT_METHODS = [
  ["card", "Card"],
  ["cash", "Cash"],
  ["venmo", "Venmo"],
  ["zelle", "Zelle"],
  ["paypal", "PayPal"],
  ["other", "Other"],
];

export function paymentLabel(method: string | null): string {
  return PAYMENT_METHODS.find(([value]) => value === method)?.[1] ?? "—";
}
