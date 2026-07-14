export type CapBucket = "Large cap" | "Mid cap" | "Small cap";

const BUCKETS: Record<CapBucket, string[]> = {
  "Large cap": [
    "RELIANCE.NS", "HDFCBANK.NS", "TCS.NS", "ICICIBANK.NS", "BHARTIARTL.NS",
    "INFY.NS", "HINDUNILVR.NS", "ITC.NS", "LT.NS", "SBIN.NS",
    "AXISBANK.NS", "KOTAKBANK.NS", "MARUTI.NS", "SUNPHARMA.NS", "TMPV.NS",
    "TATASTEEL.NS", "NTPC.NS", "POWERGRID.NS", "ULTRACEMCO.NS", "ASIANPAINT.NS",
    "WIPRO.NS", "HCLTECH.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", "TITAN.NS",
    "NESTLEIND.NS", "ADANIENT.NS", "ADANIPORTS.NS", "JSWSTEEL.NS", "HINDALCO.NS",
    "ONGC.NS", "COALINDIA.NS", "BPCL.NS", "GRASIM.NS", "DRREDDY.NS",
    "CIPLA.NS", "HEROMOTOCO.NS", "EICHERMOT.NS", "INDUSINDBK.NS", "M&M.NS",
  ],
  "Mid cap": [
    "CGPOWER.NS", "DIXON.NS", "COFORGE.NS", "PERSISTENT.NS", "MPHASIS.NS",
    "FEDERALBNK.NS", "AUBANK.NS", "PIIND.NS", "DEEPAKNTR.NS", "SRF.NS",
    "TRENT.NS", "PAGEIND.NS", "VOLTAS.NS", "INDHOTEL.NS", "LTTS.NS",
    "GODREJCP.NS", "DABUR.NS", "MARICO.NS", "BERGEPAINT.NS", "HAVELLS.NS",
    "AMBUJACEM.NS", "TORNTPHARM.NS", "LUPIN.NS", "ESCORTS.NS", "BANKBARODA.NS",
    "PNB.NS", "IDFCFIRSTB.NS", "ZYDUSLIFE.NS", "ALKEM.NS", "JUBLFOOD.NS",
  ],
  "Small cap": [
    "CDSL.NS", "IEX.NS", "CYIENT.NS", "GLENMARK.NS", "BIRLACORPN.NS",
    "CAMS.NS", "KPITTECH.NS", "RAINBOW.NS", "CLEAN.NS", "ANGELONE.NS",
    "ROUTE.NS", "LATENTVIEW.NS", "HAPPSTMNDS.NS", "GRANULES.NS", "RATNAMANI.NS",
    "POLYCAB.NS", "KEI.NS", "BLUESTARCO.NS", "APLAPOLLO.NS", "JBCHEPHARM.NS",
    "NAVINFLUOR.NS", "FINEORG.NS", "GALAXYSURF.NS", "CENTURYPLY.NS", "VGUARD.NS",
    "RADICO.NS", "METROPOLIS.NS", "LALPATHLAB.NS", "CROMPTON.NS", "IRCTC.NS",
  ],
};
// 40 large-cap / 30 mid-cap / 30 small-cap — see agents/README.md.

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
