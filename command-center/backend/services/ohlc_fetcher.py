"""
ohlc_fetcher.py — OHLC fetcher with SQLite cache.

Two fetch paths:
  - ninjatrader (default) — daily bars via yfinance proxies, cached in
    instrument_daily_ohlc. Adequate for daily-bar regime classification.
  - mt5 — intraday bars (H1/H4) via MT5 agent, cached in
    instrument_intraday_ohlc. Used for MT5 strategy regime classification.

Cache freshness: dates/timestamps older than _RECENT_DAYS are fetched once
and never refetched. The recent window is always refetched since intraday
closes may have been incomplete on first fetch.

See trading/regime/REGIME_CLASSIFIER.md for classifier data requirements.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from services import lab_db
from services import mt5_agent_client

log = logging.getLogger("OHLC")

_RECENT_DAYS = 5

# Map root CME futures symbols to yfinance tickers.
# Strip contract month before lookup: 'MNQ 06-26' → 'MNQ'.
INSTRUMENT_YFINANCE_MAP: dict[str, str] = {
    "MES":  "^GSPC",
    "ES":   "^GSPC",
    "MNQ":  "^NDX",
    "NQ":   "^NDX",
    "MGC":  "GC=F",
    "GC":   "GC=F",
    "MCL":  "CL=F",
    "CL":   "CL=F",
    "MYM":  "^DJI",
    "YM":   "^DJI",
    "M2K":  "^RUT",
    "RTY":  "^RUT",
    "M6E":  "EURUSD=X",
    "M6B":  "GBPUSD=X",
    "ZN":   "^TNX",
    "ZB":   "^TYX",
}


def _root_symbol(instrument: str) -> str:
    """Strip contract month suffix: 'MNQ 06-26' → 'MNQ', 'MGC' → 'MGC'."""
    return instrument.split()[0].upper()


def _yfinance_ticker(instrument: str) -> Optional[str]:
    return INSTRUMENT_YFINANCE_MAP.get(_root_symbol(instrument))


def _resolve_mt5_symbol(instrument: str) -> str:
    """Append broker_suffix from instrument_metadata if set; otherwise pass through."""
    meta = lab_db.get_instrument_metadata(instrument)
    if meta and meta.get("broker_suffix"):
        return instrument + meta["broker_suffix"]
    return instrument


def _fetch_yfinance(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Fetch daily OHLC from yfinance for [start, end] inclusive."""
    import yfinance as yf
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


def _fetch_mt5(instrument: str, timeframe: str, start: str, end: str) -> pd.DataFrame:
    """Fetch intraday OHLC from MT5 agent for [start, end] inclusive.

    Broker suffix is resolved here — callers use canonical names (e.g. EURUSD).
    Returns DataFrame with DatetimeIndex and open/high/low/close columns.
    Raises RuntimeError if the agent is unreachable or returns an error.
    """
    broker_symbol = _resolve_mt5_symbol(instrument)
    resp = mt5_agent_client.get_historical_data(broker_symbol, timeframe, start, end)
    bars = resp.get("bars", [])
    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close"])

    df = pd.DataFrame(bars)
    df["time"] = pd.to_datetime(df["time"])
    df = df.set_index("time")[["open", "high", "low", "close"]].sort_index()
    df.index.name = "date"
    return df


def _get_ohlc_yfinance(instrument: str, start_date: str, end_date: str) -> pd.DataFrame:
    ticker = _yfinance_ticker(instrument)
    if ticker is None:
        raise ValueError(
            f"No yfinance ticker mapping for instrument {instrument!r}. "
            f"Add the root symbol to INSTRUMENT_YFINANCE_MAP in ohlc_fetcher.py."
        )

    today = date.today()
    stale_cutoff = (today - timedelta(days=_RECENT_DAYS)).isoformat()

    cached = lab_db.get_cached_ohlc(instrument, start_date, end_date)
    cached_dates = {r["date"] for r in cached}

    fetch_start: Optional[str] = None
    fetch_end: Optional[str] = None

    old_end = min(end_date, stale_cutoff)
    if start_date <= old_end:
        old_cached_sorted = sorted(d for d in cached_dates if d <= old_end)
        if not old_cached_sorted:
            fetch_start = start_date
            fetch_end = old_end
        else:
            earliest = old_cached_sorted[0]
            start_dt = date.fromisoformat(start_date)
            earliest_dt = date.fromisoformat(earliest)
            if (earliest_dt - start_dt).days > 5:
                fetch_start = start_date
                fetch_end = earliest

    if end_date > stale_cutoff:
        recent_start = max(
            start_date,
            (date.fromisoformat(stale_cutoff) + timedelta(days=1)).isoformat(),
        )
        if fetch_start is None:
            fetch_start = recent_start
            fetch_end = end_date
        else:
            fetch_start = min(fetch_start, recent_start)
            fetch_end = end_date

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

    all_rows = lab_db.get_cached_ohlc(instrument, start_date, end_date)
    if not all_rows:
        return pd.DataFrame(columns=["open", "high", "low", "close"])

    df = pd.DataFrame(all_rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")[["open", "high", "low", "close"]].sort_index()
    return df


def _get_ohlc_mt5(
    instrument: str, start_date: str, end_date: str, timeframe: str
) -> pd.DataFrame:
    """MT5 intraday fetch path with the same cache freshness rules as the yfinance path.

    Old bars (timestamp date > _RECENT_DAYS ago) are cached once and never refetched.
    Recent bars are always refetched. Falls back to yfinance daily if timeframe is
    daily/D1 and MT5 is unreachable — for H1/H4 there is no yfinance fallback.
    """
    today = date.today()
    stale_cutoff = (today - timedelta(days=_RECENT_DAYS)).isoformat()

    cached = lab_db.get_cached_intraday_ohlc(instrument, timeframe, start_date, end_date)
    # Derive covered dates from cached timestamps for the gap check
    cached_dates = {r["timestamp"][:10] for r in cached}

    fetch_start: Optional[str] = None
    fetch_end: Optional[str] = None

    old_end = min(end_date, stale_cutoff)
    if start_date <= old_end:
        old_cached_sorted = sorted(d for d in cached_dates if d <= old_end)
        if not old_cached_sorted:
            fetch_start = start_date
            fetch_end = old_end
        else:
            earliest = old_cached_sorted[0]
            if (date.fromisoformat(earliest) - date.fromisoformat(start_date)).days > 5:
                fetch_start = start_date
                fetch_end = earliest

    if end_date > stale_cutoff:
        recent_start = max(
            start_date,
            (date.fromisoformat(stale_cutoff) + timedelta(days=1)).isoformat(),
        )
        if fetch_start is None:
            fetch_start = recent_start
            fetch_end = end_date
        else:
            fetch_start = min(fetch_start, recent_start)
            fetch_end = end_date

    if fetch_start and fetch_end:
        log.info("Fetching OHLC for %s %s [%s, %s] via MT5 agent",
                 instrument, timeframe, fetch_start, fetch_end)
        try:
            df_new = _fetch_mt5(instrument, timeframe, fetch_start, fetch_end)
            if not df_new.empty:
                new_rows = [
                    {
                        "instrument": instrument,
                        "timeframe":  timeframe,
                        "timestamp":  idx.isoformat(),
                        "open":   float(row["open"]),
                        "high":   float(row["high"]),
                        "low":    float(row["low"]),
                        "close":  float(row["close"]),
                        "source": "mt5",
                    }
                    for idx, row in df_new.iterrows()
                ]
                lab_db.upsert_intraday_ohlc_rows(new_rows)
                log.info("Cached %d intraday OHLC rows for %s %s",
                         len(new_rows), instrument, timeframe)
        except RuntimeError as exc:
            is_daily = timeframe.upper() in ("D1", "DAILY")
            if is_daily:
                log.warning(
                    "MT5 agent unreachable for %s %s — falling back to yfinance daily: %s",
                    instrument, timeframe, exc,
                )
                return _get_ohlc_yfinance(instrument, start_date, end_date)
            log.warning(
                "MT5 agent unreachable for %s %s — no yfinance fallback for intraday: %s",
                instrument, timeframe, exc,
            )

    all_rows = lab_db.get_cached_intraday_ohlc(instrument, timeframe, start_date, end_date)
    if not all_rows:
        return pd.DataFrame(columns=["open", "high", "low", "close"])

    df = pd.DataFrame(all_rows)
    df["date"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("date")[["open", "high", "low", "close"]].sort_index()
    return df


def get_ohlc(
    instrument: str,
    start_date: str,
    end_date: str,
    timeframe: str = "daily",
    runner: str = "ninjatrader",
) -> pd.DataFrame:
    """Return OHLC for instrument in [start_date, end_date].

    DataFrame has DatetimeIndex and columns: open, high, low, close, sorted ascending.
    Returns an empty DataFrame if no data is available.

    runner="ninjatrader" (default) — fetches daily bars via yfinance; caches in
        instrument_daily_ohlc. Raises ValueError if instrument has no yfinance mapping.
    runner="mt5" — fetches H1/H4/daily bars from the MT5 agent via SSH tunnel;
        caches in instrument_intraday_ohlc. Falls back to yfinance daily if the
        agent is unreachable and timeframe is daily/D1. No yfinance fallback for H1/H4.

    Cache freshness (both paths): bars older than 5 days are cached once and never
    refetched. Bars within the last 5 days are always refetched.
    """
    if runner == "mt5":
        return _get_ohlc_mt5(instrument, start_date, end_date, timeframe)
    return _get_ohlc_yfinance(instrument, start_date, end_date)
