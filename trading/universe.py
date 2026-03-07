"""S&P 500 Universe Data Provider.

Fetches price data, fundamentals, news, macro data, and industry mappings
for the S&P 500 constituents. Feeds data into the SignalEngine.
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import numpy as np

from trading.broker import AlpacaBroker

logger = logging.getLogger(__name__)

# Hardcoded top-100 S&P 500 stocks as fallback
_FALLBACK_SP500 = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "BRK.B", "LLY", "AVGO", "JPM",
    "TSLA", "UNH", "XOM", "V", "PG", "JNJ", "MA", "COST", "HD", "MRK",
    "ABBV", "CRM", "AMD", "CVX", "NFLX", "PEP", "KO", "LIN", "WMT", "TMO",
    "ACN", "ADBE", "MCD", "CSCO", "ABT", "DHR", "BAC", "CMCSA", "ORCL", "INTC",
    "DIS", "VZ", "PM", "IBM", "NOW", "INTU", "GE", "TXN", "QCOM", "AMGN",
    "CAT", "AMAT", "ISRG", "HON", "UNP", "BKNG", "GS", "MS", "AXP", "BLK",
    "LOW", "PFE", "RTX", "SPGI", "SYK", "T", "ELV", "BA", "DE", "VRTX",
    "NEE", "SCHW", "ADP", "LMT", "MDLZ", "GILD", "MMC", "CB", "TJX", "PLD",
    "CI", "SO", "DUK", "BMY", "ZTS", "SLB", "CME", "BDX", "MO", "CL",
    "EOG", "USB", "WM", "ICE", "REGN", "NOC", "APD", "SHW", "ITW", "ETN",
]


class UniverseProvider:
    """Provides S&P 500 constituent data for the multi-factor model."""

    def __init__(self, broker: Optional[AlpacaBroker] = None):
        self.broker = broker
        self._fundamentals_cache: dict[str, dict] = {}
        self._industry_cache: dict[str, str] = {}

    def get_sp500_symbols(self) -> list[str]:
        """Fetch S&P 500 constituent list from Wikipedia, fallback to hardcoded."""
        try:
            tables = pd.read_html(
                "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            )
            df = tables[0]
            symbols = df["Symbol"].str.replace(".", "-", regex=False).tolist()
            logger.info(f"Fetched {len(symbols)} S&P 500 symbols from Wikipedia")
            return symbols
        except Exception as e:
            logger.warning(f"Wikipedia fetch failed ({e}), using fallback list")
            return _FALLBACK_SP500.copy()

    def get_price_data(
        self, symbols: list[str], days: int = 504
    ) -> dict[str, pd.DataFrame]:
        """Fetch historical daily close prices for all symbols.

        Uses Alpaca if broker is available, otherwise falls back to yfinance.
        Returns {symbol: DataFrame with 'close' column and DatetimeIndex}.
        """
        if self.broker:
            result = self._get_prices_alpaca(symbols, days)
            if result:
                return result
            logger.info("Alpaca returned no data, falling back to yfinance")
        return self._get_prices_yfinance(symbols, days)

    def _get_prices_alpaca(
        self, symbols: list[str], days: int
    ) -> dict[str, pd.DataFrame]:
        """Fetch prices via Alpaca in batches."""
        result = {}
        batch_size = 50
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            try:
                bars = self.broker.get_bars(batch, "1Day", days)
                for sym in batch:
                    if sym in bars and bars[sym]:
                        bar_list = bars[sym]
                        dates = [b.timestamp for b in bar_list]
                        closes = [float(b.close) for b in bar_list]
                        if len(dates) > 0:
                            df = pd.DataFrame(
                                {"close": closes},
                                index=pd.DatetimeIndex(dates),
                            )
                            result[sym] = df
            except Exception as e:
                logger.warning(f"Alpaca batch {i//batch_size} failed: {e}")
            if i + batch_size < len(symbols):
                time.sleep(0.3)
        logger.info(f"Got price data for {len(result)}/{len(symbols)} symbols via Alpaca")
        return result

    def _get_prices_yfinance(
        self, symbols: list[str], days: int
    ) -> dict[str, pd.DataFrame]:
        """Fetch prices via yfinance as fallback."""
        import yfinance as yf

        result = {}
        batch_size = 50
        period = f"{max(1, days // 252)}y"

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            try:
                data = yf.download(
                    batch, period=period, progress=False, threads=True
                )
                if isinstance(data.columns, pd.MultiIndex):
                    for sym in batch:
                        try:
                            close = data["Close"][sym].dropna()
                            if len(close) > 100:
                                result[sym] = pd.DataFrame({"close": close.values}, index=close.index)
                        except (KeyError, TypeError):
                            pass
                elif len(batch) == 1 and "Close" in data.columns:
                    sym = batch[0]
                    close = data["Close"].dropna()
                    if len(close) > 100:
                        result[sym] = pd.DataFrame({"close": close.values}, index=close.index)
            except Exception as e:
                logger.warning(f"yfinance batch {i//batch_size} failed: {e}")
            if i + batch_size < len(symbols):
                time.sleep(0.5)

        logger.info(f"Got price data for {len(result)}/{len(symbols)} symbols via yfinance")
        return result

    def get_fundamentals(self, symbols: list[str]) -> dict[str, dict]:
        """Fetch fundamental data for value and quality factor scoring.

        Maps yfinance Ticker.info fields to the format expected by
        ValueFactor and QualityFactor.
        """
        import yfinance as yf

        result = {}
        for i, sym in enumerate(symbols):
            if sym in self._fundamentals_cache:
                result[sym] = self._fundamentals_cache[sym]
                continue
            try:
                info = yf.Ticker(sym).info
                if not info:
                    continue

                market_cap = info.get("marketCap", 0) or 0
                fcf = info.get("freeCashflow", 0) or 0
                total_assets = info.get("totalAssets", 0) or info.get("totalRevenue", 0) or 0
                ocf = info.get("operatingCashflow", 0) or 0

                fundamentals = {
                    "pe_ratio": info.get("trailingPE"),
                    "pb_ratio": info.get("priceToBook"),
                    "ev_ebitda": info.get("enterpriseToEbitda"),
                    "fcf_yield": (fcf / market_cap) if market_cap > 0 else None,
                    "roe": info.get("returnOnEquity"),
                    "debt_to_equity": (info.get("debtToEquity", 0) or 0) / 100.0,
                    "earnings_stability": 2.0,  # default — would need historical EPS
                    "ocf_to_assets": (ocf / total_assets) if total_assets > 0 else None,
                }

                # Cache sector/industry while we have the info dict
                sector = info.get("sector", "Unknown")
                self._industry_cache[sym] = sector

                result[sym] = fundamentals
                self._fundamentals_cache[sym] = fundamentals

            except Exception as e:
                logger.debug(f"Fundamentals failed for {sym}: {e}")

            # Rate limit: pause every 20 symbols
            if (i + 1) % 20 == 0 and i + 1 < len(symbols):
                time.sleep(0.5)

        logger.info(f"Got fundamentals for {len(result)}/{len(symbols)} symbols")
        return result

    def get_news_data(self, symbols: list[str]) -> dict[str, list[str]]:
        """Fetch recent news headlines for sentiment scoring.

        Returns {symbol: [headline1, headline2, ...]}.
        """
        import yfinance as yf

        result = {}
        for i, sym in enumerate(symbols):
            try:
                ticker = yf.Ticker(sym)
                news = ticker.news
                if news:
                    headlines = [
                        item.get("title", "") for item in news[:5]
                        if item.get("title")
                    ]
                    if headlines:
                        result[sym] = headlines
            except Exception:
                pass

            if (i + 1) % 30 == 0 and i + 1 < len(symbols):
                time.sleep(0.3)

        logger.info(f"Got news for {len(result)}/{len(symbols)} symbols")
        return result

    def get_macro_data(self) -> dict:
        """Fetch macro data: VIX, yield curve, credit spreads."""
        import yfinance as yf

        data = {}

        # VIX
        try:
            vix = yf.Ticker("^VIX")
            hist = vix.history(period="1d")
            data["vix"] = float(hist["Close"].iloc[-1]) if not hist.empty else 20.0
        except Exception:
            data["vix"] = 20.0

        # 10-year Treasury yield
        try:
            tnx = yf.Ticker("^TNX")
            hist = tnx.history(period="1d")
            data["yield_10y"] = float(hist["Close"].iloc[-1]) if not hist.empty else 4.0
        except Exception:
            data["yield_10y"] = 4.0

        # 2-year Treasury yield
        try:
            twoy = yf.Ticker("2YY=F")
            hist = twoy.history(period="1d")
            data["yield_2y"] = float(hist["Close"].iloc[-1]) if not hist.empty else 3.5
        except Exception:
            data["yield_2y"] = 3.5

        # Credit spread (use HYG-LQD spread as proxy)
        try:
            hyg = yf.Ticker("HYG").history(period="5d")
            lqd = yf.Ticker("LQD").history(period="5d")
            if not hyg.empty and not lqd.empty:
                # Simplified: yield difference approximated by price ratio
                data["credit_spread"] = 200  # bps, simplified default
            else:
                data["credit_spread"] = 150
        except Exception:
            data["credit_spread"] = 150

        logger.info(f"Macro data: VIX={data['vix']:.1f}, 10Y={data['yield_10y']:.2f}")
        return data

    def get_industry_map(self, symbols: list[str]) -> dict[str, str]:
        """Get GICS sector for each symbol. Uses cache from get_fundamentals()."""
        import yfinance as yf

        result = {}
        uncached = []

        for sym in symbols:
            if sym in self._industry_cache:
                result[sym] = self._industry_cache[sym]
            else:
                uncached.append(sym)

        # Fetch remaining
        for i, sym in enumerate(uncached):
            try:
                info = yf.Ticker(sym).info
                sector = info.get("sector", "Unknown") if info else "Unknown"
                result[sym] = sector
                self._industry_cache[sym] = sector
            except Exception:
                result[sym] = "Unknown"

            if (i + 1) % 30 == 0:
                time.sleep(0.3)

        return result
