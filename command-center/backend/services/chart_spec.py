"""
chart_spec.py — emit a ChartSpec for the backtest chart panel (frontend ChartPanel).

Phase 7a: candles + sessions + trades from a finished run.
Phase 7b: strategy-structure overlays + indicators, recomputed server-side from the run's
params + candles (the strategy doesn't log them). Currently wired for the London-breakout
family (detected by the `AsianStartGMT` param); other strategies get empty structure.

The spec is the contract the panel reads (see
command-center/frontend/src/components/ChartPanel/types.ts). Times are epoch MILLISECONDS,
UTC. Field names are camelCase to match that contract — this is the one place the backend
emits camelCase, because the shape is defined by the chart, not a DB model.

Data sources:
  - candles: services.ohlc_fetcher (intraday M-bars for MT5; daily for NT8).
  - trades:  reconstructed from the stored equity_curve.json. MT5 stores each trade as a pair
             of deal points (entry: profit 0, exit: realized profit); we pair them to recover
             entry/exit time + direction, and read prices off the candles at those times.
  - sessions: generic FX market sessions (config, not strategy logic).
  - overlays/indicators (7b): recomputed from M15 candles + the daily ATR, matching
    strategies/mt5/LondonBreakout.mq5 (Asian range box, ATR-buffered buy/sell levels, ATR pane).
    This is a RECONSTRUCTION from the same inputs the strategy used — not a strategy-logged
    artifact. It is server-side, so the chart itself still computes no strategy structure.

Broker offset: the MT5 deal/bar timestamps are GMT (the force-flat at 11:00 lands at 11:00),
so brokerGmtOffsetHours is 0 and both axes are UTC.
"""

from __future__ import annotations

import bisect
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from services import lab_db, ohlc_fetcher
from services.backtest_runner import LAB_RESULTS_DIR

log = logging.getLogger("CHARTSPEC")

# Generic FX market sessions — data, not strategy logic. Times are local to each `tz`.
_FX_SESSIONS = [
    {"name": "Tokyo",    "tz": "Asia/Tokyo",        "start": "09:00", "end": "15:00", "color": "#8b5cf6"},
    {"name": "London",   "tz": "Europe/London",     "start": "08:00", "end": "16:30", "color": "#00e5ff"},
    {"name": "New York", "tz": "America/New_York",  "start": "08:00", "end": "17:00", "color": "#e6bd6a"},
]


def _base_timeframe(bar_type: Optional[str], bar_value: Optional[int]) -> str:
    """NT8/MT5 bar config → a TF string the panel understands (M5/M15/M30/H1/H4/D1)."""
    bt = (bar_type or "Minute").lower()
    v = int(bar_value or 15)
    if bt.startswith("day"):
        return "D1"
    if v >= 60 and v % 60 == 0:
        return f"H{v // 60}"
    return f"M{v}"


_TF_MIN = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
_TF_LADDER = ["M5", "M15", "M30", "H1", "H4", "D1"]
_CANDLE_CAP = 35_000  # keeps ~1yr at M15; a 5yr run steps up to H1 instead of ~125k M15 candles


def _fit_timeframe(base_tf: str, start_date: str, end_date: str) -> str:
    """Step the base TF up to a coarser one when a full intraday fetch over the span would be too
    many candles to ship/render. Returns base_tf unchanged when it already fits under the cap."""
    if base_tf not in _TF_LADDER:
        return base_tf
    try:
        span_days = max(1, (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days)
    except ValueError:
        return base_tf
    for tf in _TF_LADDER[_TF_LADDER.index(base_tf):]:
        bars = (1440 / _TF_MIN[tf]) * (5 / 7) * span_days  # ~forex: 5 trading days/week, 24h
        if bars <= _CANDLE_CAP:
            return tf
    return "D1"


def _ts_to_epoch_ms(ts) -> int:
    """pandas Timestamp / datetime → epoch ms (UTC). Naive values are treated as UTC."""
    dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _iso_to_epoch_ms(s: str) -> Optional[int]:
    try:
        dt = datetime.fromisoformat(s.replace("Z", ""))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _build_candles(instrument: str, start_date: str, end_date: str, base_tf: str, runner: str) -> list[dict]:
    # ohlc_fetcher normalizes the symbol (strips the broker suffix, re-adds a configured one), so
    # we can pass the run instrument as-is — the MT5 agent's terminal uses plain names.
    try:
        df = ohlc_fetcher.get_ohlc(instrument, start_date, end_date, timeframe=base_tf, runner=runner)
    except Exception as exc:  # noqa: BLE001 — fetch is best-effort; empty candles degrade gracefully
        log.warning("chart_spec: candle fetch failed for %s %s: %s", instrument, base_tf, exc)
        return []
    if df is None or df.empty:
        return []
    candles = [
        {
            "time": _ts_to_epoch_ms(idx),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        }
        for idx, row in df.iterrows()
    ]
    candles.sort(key=lambda c: c["time"])
    return candles


def _build_trades(equity_curve: list[dict], candles: list[dict]) -> list[dict]:
    """Pair the equity curve's deal points (entry, exit) into trades. Prices are read off the
    candles at the deal times (the run doesn't store fill prices). Needs candles for prices."""
    if not candles:
        return []
    times = [c["time"] for c in candles]

    def price_at(epoch: int) -> Optional[float]:
        i = bisect.bisect_right(times, epoch) - 1
        if i < 0:
            i = 0
        return candles[i]["close"]

    # Skip the opening-balance point (no direction); pair the rest entry→exit.
    pts = [p for p in equity_curve if p.get("direction")]
    trades: list[dict] = []
    for k in range(0, len(pts) - 1, 2):
        entry, exit_ = pts[k], pts[k + 1]
        et = _iso_to_epoch_ms(entry.get("date", ""))
        xt = _iso_to_epoch_ms(exit_.get("date", ""))
        if et is None or xt is None:
            continue
        ep, xp = price_at(et), price_at(xt)
        if ep is None or xp is None:
            continue
        direction = "short" if (entry.get("direction") or "").strip().lower().startswith("s") else "long"
        trades.append({
            "id": f"T{k // 2 + 1}",
            "dir": direction,
            "entryTime": et,
            "entryPrice": ep,
            "exitTime": xt,
            "exitPrice": xp,
            "exitReason": exit_.get("exit_name") or "",
        })
    return trades


# ── Strategy structure (Phase 7b) — London-breakout family ─────────────────────────
_DAY_MS = 24 * 60 * 60 * 1000


def _hhmm_to_ms(s: str, default_min: int) -> int:
    try:
        h, m = s.split(":")
        return (int(h) * 60 + int(m)) * 60_000
    except (ValueError, AttributeError):
        return default_min * 60_000


def _wilder_atr(daily: list[dict], period: int) -> dict[int, float]:
    """Wilder ATR(period) over daily bars → {day_time_ms: atr}. Matches MT5 iATR."""
    if len(daily) < period + 1:
        return {}
    trs = []
    for i in range(1, len(daily)):
        h, lo, pc = daily[i]["high"], daily[i]["low"], daily[i - 1]["close"]
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    out: dict[int, float] = {}
    atr = sum(trs[:period]) / period            # seed = SMA of first `period` TRs
    out[daily[period]["time"]] = atr            # trs[i] belongs to daily[i+1]
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
        out[daily[i + 1]["time"]] = atr
    return out


def _build_structure(
    m15: list[dict], trades: list[dict], daily: list[dict], params: dict,
) -> tuple[list[dict], list[dict]]:
    """Recompute the London-breakout structure (Asian range box + ATR-buffered buy/sell levels)
    for each day a trade occurred, plus the daily ATR series as a sub-pane indicator."""
    period = int(params.get("AtrPeriod", 14) or 14)
    buffer_atr = float(params.get("BufferAtr", 0.1) or 0.1)
    a_start = _hhmm_to_ms(params.get("AsianStartGMT", "00:00"), 0)
    a_end = _hhmm_to_ms(params.get("AsianEndGMT", "06:00"), 360)
    flat = _hhmm_to_ms(params.get("ForceFlatGMT", "11:00"), 660)

    atr_by_time = _wilder_atr(daily, period)
    daily_times = sorted(atr_by_time)
    atr_series = [{"time": t, "value": round(atr_by_time[t], 5)} for t in daily_times]

    def atr_before(day_ms: int) -> Optional[float]:
        # The strategy uses the last COMPLETED daily ATR (shift 1) → bar strictly before today.
        i = bisect.bisect_left(daily_times, day_ms) - 1
        return atr_by_time[daily_times[i]] if i >= 0 else None

    m15_times = [c["time"] for c in m15]
    overlays: list[dict] = []
    seen: set[int] = set()
    for tr in trades:
        day = (tr["entryTime"] // _DAY_MS) * _DAY_MS
        if day in seen:
            continue
        seen.add(day)
        a0, a1, t_flat = day + a_start, day + a_end, day + flat
        lo_i = bisect.bisect_left(m15_times, a0)
        hi_i = bisect.bisect_left(m15_times, a1)
        window = m15[lo_i:hi_i]
        if not window:
            continue
        hi = max(c["high"] for c in window)
        low = min(c["low"] for c in window)
        overlays.append({
            "type": "box", "group": "Asian range", "t0": a0, "t1": a1,
            "top": hi, "bottom": low, "style": {"color": "#e6bd6a"},
        })
        atr = atr_before(day)
        if atr:
            overlays.append({
                "type": "hline", "group": "Breakout levels", "t0": a1, "t1": t_flat,
                "price": round(hi + buffer_atr * atr, 5), "label": "Buy",
                "style": {"color": "#33ff99", "lineStyle": "dashed"},
            })
            overlays.append({
                "type": "hline", "group": "Breakout levels", "t0": a1, "t1": t_flat,
                "price": round(low - buffer_atr * atr, 5), "label": "Sell",
                "style": {"color": "#ff6680", "lineStyle": "dashed"},
            })

    indicators = [{
        "name": f"ATR({period}) D1", "params": {"period": period},
        "pane": "sub", "series": atr_series,
    }] if atr_series else []
    return overlays, indicators


def build_chart_spec(run_id: str, refresh: bool = False) -> Optional[dict]:
    """Build (and cache) the ChartSpec for a completed run. Returns None if the run is unknown.
    Cached to reports/lab/<run_id>/chart_spec.json; pass refresh=True to rebuild."""
    row = lab_db.get_run(run_id)
    if not row:
        return None

    run_dir = LAB_RESULTS_DIR / run_id
    spec_path = run_dir / "chart_spec.json"
    if spec_path.exists() and not refresh:
        try:
            return json.loads(spec_path.read_text())
        except (ValueError, OSError):
            pass  # rebuild on a corrupt cache

    runner = row.get("runner") or "ninjatrader"
    instrument = row["instrument"]
    # NT8 only has daily bars today; MT5 ideally has intraday from the agent. Cap the candle
    # volume by stepping the TF up for long spans (a 5yr run → H1, not ~125k M15 candles).
    base_tf = _base_timeframe(row.get("bar_type"), row.get("bar_value")) if runner == "mt5" else "D1"
    if runner == "mt5":
        base_tf = _fit_timeframe(base_tf, row["start_date"], row["end_date"])

    candles = _build_candles(instrument, row["start_date"], row["end_date"], base_tf, runner)
    # Fallback: the MT5 agent can't always serve intraday history (symbol not selected, or the
    # run's sub-hour TF unsupported). Daily bars come from yfinance via the D1 path — coarse, but
    # a real price chart beats none. baseTimeframe reflects what actually loaded.
    if not candles and base_tf != "D1":
        candles = _build_candles(instrument, row["start_date"], row["end_date"], "D1", runner)
        if candles:
            base_tf = "D1"

    equity_curve: list[dict] = []
    eq_path = row.get("equity_curve_path")
    if eq_path:
        try:
            equity_curve = json.loads(Path(eq_path).read_text())
        except (ValueError, OSError):
            equity_curve = []
    trades = _build_trades(equity_curve, candles)

    # Strategy structure (7b): recompute when we have intraday candles and the run is a
    # London-breakout (detected by its params). Needs daily bars (with warmup) for the ATR.
    overlays: list[dict] = []
    indicators: list[dict] = []
    params = row.get("params") or {}
    if base_tf != "D1" and "AsianStartGMT" in params:
        warmup_start = (date.fromisoformat(row["start_date"]) - timedelta(days=40)).isoformat()
        daily = _build_candles(instrument, warmup_start, row["end_date"], "D1", runner)
        overlays, indicators = _build_structure(candles, trades, daily, params)

    spec = {
        "instrument": instrument,
        "baseTimeframe": base_tf,
        "brokerGmtOffsetHours": 0,
        "candles": candles,
        "sessions": [dict(s) for s in _FX_SESSIONS],
        "trades": trades,
        "overlays": overlays,
        "indicators": indicators,
    }

    run_dir.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec))
    log.info("chart_spec: built for %s — %d candles, %d trades, %d overlays, %d indicators (%s)",
             run_id, len(candles), len(trades), len(overlays), len(indicators), base_tf)
    return spec
