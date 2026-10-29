/** Formatting helpers. Cents stay integers until the last moment; the UI never adds floats. */

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const num = new Intl.NumberFormat("en-US");

export function cents(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  const dollars = Math.floor(abs / 100);
  const rem = abs % 100;
  // Build from integers so 25_505_253 cents is exactly $255,052.53.
  return `${sign}${usd.format(dollars).replace(/\.00$/, "")}.${String(rem).padStart(2, "0")}`;
}

export function count(value: number | null | undefined): string {
  return value === null || value === undefined ? "-" : num.format(value);
}

export function when(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export function label(code: string): string {
  return code.replace(/_/g, " ");
}
