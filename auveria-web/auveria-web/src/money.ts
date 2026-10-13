// Money is integer kobo everywhere. Floats never touch an amount.

function group(whole: number): string {
  return whole.toLocaleString("en-NG");
}

export function formatNaira(kobo: number | null): string {
  if (kobo === null) return "No limit";
  const sign = kobo < 0 ? "-" : "";
  const abs = Math.abs(kobo);
  return `${sign}₦${group(Math.floor(abs / 100))}.${String(abs % 100).padStart(2, "0")}`;
}

export function splitNaira(kobo: number): { whole: string; frac: string } {
  const abs = Math.abs(kobo);
  return { whole: group(Math.floor(abs / 100)), frac: String(abs % 100).padStart(2, "0") };
}

/** "25,000.50" -> 2500050. Returns null for anything that isn't a positive amount with at most 2 decimals. */
export function parseNairaToKobo(input: string): number | null {
  const text = input.replace(/[,\s₦]/g, "");
  if (!/^\d+(\.\d{1,2})?$/.test(text)) return null;
  const [whole, frac = ""] = text.split(".");
  const kobo = Number(whole) * 100 + Number(frac.padEnd(2, "0"));
  if (!Number.isSafeInteger(kobo) || kobo <= 0) return null;
  return kobo;
}
