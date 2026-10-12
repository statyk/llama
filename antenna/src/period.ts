/** Cloudflare billing periods are anniversary-based (UTC), not calendar months
 * (spec "Platform facts"). The anniversary day comes from the Billing page. */

export interface Period {
  startMs: number;
  endMs: number;
}

/** Midnight UTC on `day` of the month; a month without that day uses its last day. */
function anniversary(year: number, month: number, day: number): number {
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return Date.UTC(year, month, Math.min(day, lastDay));
}

export function billingPeriod(nowMs: number, day: number): Period {
  if (!Number.isInteger(day) || day < 1 || day > 31) {
    throw new Error(`billing anniversary day must be an integer 1..31, not ${day}`);
  }
  const now = new Date(nowMs);
  let year = now.getUTCFullYear();
  let month = now.getUTCMonth();
  let startMs = anniversary(year, month, day);
  if (startMs > nowMs) {
    month -= 1;
    if (month < 0) {
      month = 11;
      year -= 1;
    }
    startMs = anniversary(year, month, day);
  }
  const endMs = month === 11 ? anniversary(year + 1, 0, day) : anniversary(year, month + 1, day);
  return { startMs, endMs };
}
