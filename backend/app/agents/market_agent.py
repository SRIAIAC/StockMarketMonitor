import datetime as dt
import logging

import httpx
import yfinance as yf

from app.agents.base import BaseAgent
from app.config import settings
from app.models import Price

logger = logging.getLogger(__name__)

MONEYCONTROL_CODES = {
    "RELIANCE.NS": "RI",
    "HDFCBANK.NS": "HDF01",
    "TCS.NS": "TCS",
    "ICICIBANK.NS": "ICI02",
    "BHARTIARTL.NS": "BTV",
    "CGPOWER.NS": "CG",
    "DIXON.NS": "DT07",
    "COFORGE.NS": "NII02",
    "PERSISTENT.NS": "PS15",
    "MPHASIS.NS": "BFL",
    "CDSL.NS": "CDS",
    "IEX.NS": "IEE",
    "CYIENT.NS": "IE07",
    "GLENMARK.NS": "GP08",
    "BIRLACORPN.NS": "BC07",
}

MONEYCONTROL_URL = "https://priceapi.moneycontrol.com/pricefeed/nse/equitycash/{code}"
MONEYCONTROL_HEADERS = {"User-Agent": "Mozilla/5.0 StockMarketMonitor/0.1"}


class MarketAgent(BaseAgent):
    name = "market"

    def run(self) -> None:
        tickers = settings.tickers
        history = None
        data = None
        session = self.session()
        try:
            with httpx.Client(headers=MONEYCONTROL_HEADERS, timeout=10) as client:
                for symbol in tickers:
                    price = None
                    prev_close = None
                    volume = 0
                    avg_volume = None
                    sector = None

                    moneycontrol_quote = self._moneycontrol_quote(client, symbol)
                    if moneycontrol_quote is not None:
                        price, prev_close, volume, avg_volume, sector = moneycontrol_quote

                    if price is None or prev_close in (None, 0):
                        if history is None:
                            history = yf.download(
                                tickers,
                                period="5d",
                                group_by="ticker",
                                auto_adjust=False,
                                progress=False,
                                threads=True,
                            )
                        price, prev_close, volume = self._latest_from_history(history, symbol, len(tickers) > 1)

                    if price is None or prev_close in (None, 0):
                        if data is None:
                            data = yf.Tickers(" ".join(tickers))
                        info = data.tickers.get(symbol)
                        if info is not None:
                            try:
                                fast = info.fast_info
                                price = fast.get("lastPrice")
                                prev_close = fast.get("previousClose")
                                volume = fast.get("lastVolume") or 0
                                avg_volume = fast.get("threeMonthAverageVolume")
                            except Exception:
                                logger.warning("Quote lookup failed for %s", symbol)

                    if price is None or prev_close in (None, 0):
                        continue

                    pct_change = (price - prev_close) / prev_close * 100

                    if sector is None:
                        try:
                            if data is None:
                                data = yf.Tickers(" ".join(tickers))
                            info = data.tickers.get(symbol)
                            sector = info.get_info().get("sector")
                        except Exception:
                            pass

                    session.add(
                        Price(
                            ticker=symbol,
                            sector=sector,
                            price=price,
                            prev_close=prev_close,
                            pct_change=pct_change,
                            volume=int(volume),
                            avg_volume=int(avg_volume) if avg_volume else None,
                            fetched_at=dt.datetime.utcnow(),
                        )
                    )
            session.commit()
        finally:
            session.close()

    @staticmethod
    def _latest_from_history(history, symbol: str, multi_ticker: bool):
        try:
            frame = history[symbol] if multi_ticker else history
            if frame.empty:
                return None, None, 0

            closes = frame["Close"].dropna()
            if closes.empty:
                return None, None, 0

            price = float(closes.iloc[-1])
            prev_close = float(closes.iloc[-2]) if len(closes) > 1 else None
            volume_series = frame["Volume"].dropna()
            volume = int(volume_series.iloc[-1]) if not volume_series.empty else 0
            return price, prev_close, volume
        except Exception:
            return None, None, 0

    @staticmethod
    def _moneycontrol_quote(client: httpx.Client, symbol: str):
        code = MONEYCONTROL_CODES.get(symbol)
        if not code:
            return None

        try:
            resp = client.get(MONEYCONTROL_URL.format(code=code))
            resp.raise_for_status()
            payload = resp.json().get("data", {})
            price = _to_float(payload.get("pricecurrent"))
            prev_close = _to_float(payload.get("priceprevclose"))
            volume = int(_to_float(payload.get("VOL")) or 0)
            avg_volume = _to_float(payload.get("DVolAvg20"))
            sector = payload.get("newSubsector") or payload.get("SC_SUBSEC")
        except Exception:
            logger.warning("Moneycontrol quote lookup failed for %s", symbol)
            return None

        if price is None or prev_close in (None, 0):
            return None
        return price, prev_close, volume, avg_volume, sector


def _to_float(value):
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None
