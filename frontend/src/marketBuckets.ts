export type CapBucket = "Large cap" | "Mid cap" | "Small cap";

const BUCKETS: Record<CapBucket, string[]> = {
  "Large cap": [
    "RELIANCE.NS", "HDFCBANK.NS", "TCS.NS", "ICICIBANK.NS", "BHARTIARTL.NS",
    "INFY.NS", "HINDUNILVR.NS", "ITC.NS", "LT.NS", "SBIN.NS",
    "AXISBANK.NS", "KOTAKBANK.NS", "MARUTI.NS", "SUNPHARMA.NS", "TMPV.NS",
    "TATASTEEL.NS", "NTPC.NS", "POWERGRID.NS", "ULTRACEMCO.NS", "ASIANPAINT.NS",
  ],
  "Mid cap": [
    "CGPOWER.NS", "DIXON.NS", "COFORGE.NS", "PERSISTENT.NS", "MPHASIS.NS",
    "FEDERALBNK.NS", "AUBANK.NS", "PIIND.NS", "DEEPAKNTR.NS", "SRF.NS",
    "TRENT.NS", "PAGEIND.NS", "VOLTAS.NS", "INDHOTEL.NS", "LTTS.NS",
  ],
  "Small cap": [
    "CDSL.NS", "IEX.NS", "CYIENT.NS", "GLENMARK.NS", "BIRLACORPN.NS",
    "CAMS.NS", "KPITTECH.NS", "RAINBOW.NS", "CLEAN.NS", "ANGELONE.NS",
    "ROUTE.NS", "LATENTVIEW.NS", "HAPPSTMNDS.NS", "GRANULES.NS", "RATNAMANI.NS",
  ],
};
// 20 large-cap / 15 mid-cap / 15 small-cap — see agents/README.md.

export const CAP_BUCKETS = Object.entries(BUCKETS).map(([bucket, tickers]) => ({
  bucket: bucket as CapBucket,
  tickers,
}));

export function capBucketFor(ticker: string): CapBucket {
  const normalized = ticker.toUpperCase();
  return CAP_BUCKETS.find((entry) => entry.tickers.includes(normalized))?.bucket ?? "Large cap";
}

export function displayTicker(ticker: string): string {
  return ticker.replace(".NS", "");
}
