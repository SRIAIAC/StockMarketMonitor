/** NSE cash-market session: 09:15-15:30 IST, Monday-Friday. No holiday
 * calendar (would need a data source) — a real open/closed read for the
 * common case, not a hardcoded label. */

const IST_OFFSET_MIN = 5 * 60 + 30;

function nowIST(): Date {
  const now = new Date();
  const utcMs = now.getTime() + now.getTimezoneOffset() * 60_000;
  return new Date(utcMs + IST_OFFSET_MIN * 60_000);
}

export function isMarketOpen(): boolean {
  const ist = nowIST();
  const day = ist.getDay(); // 0=Sun..6=Sat, in the shifted "IST" wall-clock
  if (day === 0 || day === 6) return false;
  const minutesSinceMidnight = ist.getHours() * 60 + ist.getMinutes();
  return minutesSinceMidnight >= 9 * 60 + 15 && minutesSinceMidnight <= 15 * 60 + 30;
}

export function marketStatusLabel(): string {
  return isMarketOpen() ? "Market Open" : "Market Closed";
}
