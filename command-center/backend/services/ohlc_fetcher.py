"""
ohlc_fetcher.py — Daily OHLC fetcher with SQLite cache.

NT8 historical data extraction was evaluated and not implemented. Driving the NT8
Market Analyzer or Strategy Analyzer for data export via pywinauto requires
significant screen-automation work that cannot be tested without an interactive VPS
session. yfinance index proxies provide adequate daily-bar accuracy for regime
classification purposes. Decision: yfinance-only.

See trading/regime/REGIME_CLASSIFIER.md for the classifier's data requirements.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from services import lab_db

log = logging.getLogger("OHLC")

_RECENT_DAYS = 5  # dates within this window are always refetched (data may be incomplete)

# Map root CME futures symbols to yfinance tickers.
# These are index/proxy tickers — good enough for daily-bar regime classification.
# Strip contract month before lookup: 'MNQ 06-26' → 'MNQ'.
INSTRUMENT_YFINANCE_MAP: dict[str, str] = {
    "MES":  "^GSPC",    # S&P 500 index (proxy for Micro E-mini S&P)
    "ES":   "^GSPC",    # E-mini S&P 500
    "MNQ":  "^NDX",     # Nasdaq 100 index (proxy for Micro E-mini Nasdaq)
    "NQ":   "^NDX",     # E-mini Nasdaq 100
    "MGC":  "GC=F",     # Gold futures
    "GC":   "GC=F",
    "MCL":  "CL=F",     # Crude oil futures
    "CL":   "CL=F",
    "MYM":  "^DJI",     # Dow Jones (proxy for Micro E-mini Dow)
    "YM":   "^DJI",     # E-mini Dow
    "M2K":  "^RUT",     # Russell 2000 (proxy for Micro E-mini Russell)
    "RTY":  "^RUT",     # E-mini Russell 2000
    "M6E":  "EURUSD=X", # Micro Euro FX
    "M6B":  "GBPUSD=X", # Micro British Pound
    "ZN":   "^TNX",     # 10-Year Treasury Note
    "ZB":   "^TYX",     # 30-Year Treasury Bond
}


def _root_symbol(instrument: str) -> str:
    """Strip contract month suffix: 'MNQ 06-26' → 'MNQ', 'MGC' → 'MGC'."""
    return instrument.split()[0].upper()


def _yfinance_ticker(instrument: str) -> Optional[str]:
    return INSTRUMENT_YFINANCE_MAP.get(_root_symbol(instrument))


def _fetch_yfinance(ticker: str, start: str, end: str) -> pd.DataFrame:
    """
    Fetch daily OHLC from yfinance for [start, end] inclusive.
    Returns DataFrame with DatetimeIndex (date) and columns: open, high, low, close.
    Empty DataFrame if no data returned.
    """
    import yfinance as yf
    # yfinance end date is exclusive — add one day
    end_exclusive = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    try:
        raw = yf.Ticker(ticker).history(
            start=start, end=end_exclusive, interval="1d", auto_adjust=True
        )
    except Exception as exc:
        log.error("yfinance fetch failed for %s [%s, %s]: %s", ticker, start, end, exc)
        raise

    if raw.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])

    df = raw[["Open", "High", "Low", "Close"]].copy()
    df.columns = ["open", "high", "low", "close"]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "date"
    return df.sort_index()


def get_ohlc(instrument: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Return daily OHLC for instrument in [start_date, end_date].

    DataFrame has DatetimeIndex (date) and columns: open, high, low, close,
    sorted ascending. Empty DataFrame if no data is available.

    Caches in instrument_daily_ohlc. Old dates (> 5 days ago) are fetched once
    and never refetched. Recent dates are always refetched since the close may
    have been incomplete on first fetch.

    Raises ValueError if the instrument has no yfinance mapping.
    Raises exceptions from yfinance on network failures.
    """
    ticker = _yfinance_ticker(instrument)
    if ticker is None:
        raise ValueError(
            f"No yfinance ticker mapping for instrument {instrument!r}. "
            f"Add the root symbol to INSTRUMENT_YFINANCE_MAP in ohlc_fetcher.py."
        )

    today = date.today()
    stale_cutoff = (today - timedelta(days=_RECENT_DAYS)).isoformat()

    # ── Determine what to fetch ───────────────────────────────────────────────

    cached = lab_db.get_cached_ohlc(instrument, start_date, end_date)
    cached_dates = {r["date"] for r in cached}

    fetch_start: Optional[str] = None
    fetch_end: Optional[str] = None

    # Old range [start_date, min(end_date, stale_cutoff)]:
    # Fetch only if cache has a gap at the beginning.
    old_end = min(end_date, stale_cutoff)
    if start_date <= old_end:
        old_cached_sorted = sorted(d for d in cached_dates if d <= old_end)
        if not old_cached_sorted:
            # Nothing cached in the old range at all
            fetch_start = start_date
            fetch_end = old_end
        else:
            earliest = old_cached_sorted[0]
            start_dt = date.fromisoformat(start_date)
            earliest_dt = date.fromisoformat(earliest)
            # Gap at start? Allow 5 calendar days of buffer for weekends/holidays.
            if (earliest_dt - start_dt).days > 5:
                fetch_start = start_date
                fetch_end = earliest

    # Recent range [stale_cutoff+1, end_date]: always refetch
    if end_date > stale_cutoff:
        recent_start = max(
            start_date,
            (date.fromisoformat(stale_cutoff) + timedelta(days=1)).isoformat(),
        )
        if fetch_start is None:
            fetch_start = recent_start
            fetch_end = end_date
        else:
            # Expand to cover both the old gap and the recent window
            fetch_start = min(fetch_start, recent_start)
            fetch_end = end_date

    # ── Fetch and cache ───────────────────────────────────────────────────────

    if fetch_start and fetch_end:
        log.info("Fetching OHLC for %s [%s, %s] via yfinance (%s)",
                 instrument, fetch_start, fetch_end, ticker)
        df_new = _fetch_yfinance(ticker, fetch_start, fetch_end)
        if not df_new.empty:
            new_rows = [
                {
                    "instrument": instrument,
                    "date": idx.date().isoformat(),
                    "open":  float(row["open"]),
                    "high":  float(row["high"]),
                    "low":   float(row["low"]),
                    "close": float(row["close"]),
                    "source": "yfinance",
                }
                for idx, row in df_new.iterrows()
            ]
            lab_db.upsert_ohlc_rows(new_rows)
            log.info("Cached %d OHLC rows for %s", len(new_rows), instrument)

    # ── Return from cache ─────────────────────────────────────────────────────

    all_rows = lab_db.get_cached_ohlc(instrument, start_date, end_date)
    if not all_rows:
        return pd.DataFrame(columns=["open", "high", "low", "close"])

    df = pd.DataFrame(all_rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")[["open", "high", "low", "close"]].sort_index()
    return df
