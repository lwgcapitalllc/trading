"""
chart_spec.py — emit a ChartSpec for the backtest chart panel (frontend ChartPanel).

Phase 7a: candles + sessions + trades from a finished run. Overlays (strategy structure)
and indicators are left empty — they aren't captured by any run today (Phase 7b).

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

Broker offset: the MT5 deal/bar timestamps are GMT (the force-flat at 11:00 lands at 11:00),
so brokerGmtOffsetHours is 0 and both axes are UTC.
"""

from __future__ import annotations

import bisect
import json
import logging
from datetime import datetime, timezone
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
    # ohlc_fetcher expects the CANONICAL (root) symbol — its resolver re-adds the broker suffix
    # from instrument_metadata when one is configured. Passing the already-suffixed run symbol
    # (e.g. "USDJPY.s") double-handles it and the MT5 agent's terminal (plain names) finds nothing.
    symbol = ohlc_fetcher._root_symbol(instrument) if runner == "mt5" else instrument
    try:
        df = ohlc_fetcher.get_ohlc(symbol, start_date, end_date, timeframe=base_tf, runner=runner)
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
    # NT8 only has daily bars today; MT5 ideally has intraday from the agent.
    base_tf = _base_timeframe(row.get("bar_type"), row.get("bar_value")) if runner == "mt5" else "D1"

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

    spec = {
        "instrument": instrument,
        "baseTimeframe": base_tf,
        "brokerGmtOffsetHours": 0,
        "candles": candles,
        "sessions": [dict(s) for s in _FX_SESSIONS],
        "trades": trades,
        "overlays": [],
        "indicators": [],
    }

    run_dir.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec))
    log.info("chart_spec: built for %s — %d candles, %d trades (%s)",
             run_id, len(candles), len(trades), base_tf)
    return spec
