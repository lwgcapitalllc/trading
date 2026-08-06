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
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from services import lab_db, ohlc_fetcher
from services.backtest_runner import LAB_RESULTS_DIR
from services.fvg_overlays import GROUP_FVG, build_fvg_overlays
from services.ob_overlays import GROUP_OB, build_ob_overlays
from services.structure_overlays import build_market_structure_overlays
from services.vwap_overlays import build_vwap_indicator

log = logging.getLogger("CHARTSPEC")

# Generic FX market sessions — data, not strategy logic. Times are local to each `tz`.
_FX_SESSIONS = [
    {"name": "Tokyo",    "tz": "Asia/Tokyo",        "start": "09:00", "end": "15:00", "color": "#f472b6"},
    {"name": "London",   "tz": "Europe/London",     "start": "08:00", "end": "16:30", "color": "#60a5fa"},
    {"name": "New York", "tz": "America/New_York",  "start": "08:00", "end": "17:00", "color": "#fb923c"},
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


_TF_MIN = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
# Drill-down loads the broker's FULL sub-base depth in one shot (M5's ~240d ≈ 49k candles). Nothing
# clips it but the broker's own history, so the ONLY left edge the user hits is the real data
# boundary (the red "no earlier data" line) rather than a cap of ours.
#
# 🟢 **There is no base-chart candle cap any more (2026-08-06).** `_CANDLE_CAP` / `_capped_start`
# trimmed the spec to the newest ~35k bars and the panel PAGED the rest in on scroll-left, calling
# back for each window's analysis (`_page_analysis`). Measured, that design was 7x more expensive
# than building the run once: a page cost ~7.2s of analysis replay and a deep jump took ~14 of them
# (90.3s in a real browser), against 17.8s for one full-history build that is then cached and served
# in 0.004s for ever. The spec now carries the whole run — see `build_chart_spec` — and the panel
# applies a WINDOW of it to klinecharts, extending that window from memory.
_DRILL_CANDLE_CAP = 60_000
# A left edge shorter than what was requested is the broker's TRUE limit only when the gap exceeds a
# long weekend / holiday (bars are absent then too, but that isn't a data boundary).
_HARD_EDGE_SLOP_MS = 4 * 24 * 60 * 60 * 1000


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
    # Column-at-a-time, NOT `df.iterrows()`. Measured 2026-08-06 on a real 155,776-bar run:
    # 12.63s by iterrows against 0.15s here, byte-identical output — 85x, paid on every chart
    # request. `iterrows` builds a fresh Series per row, which is the whole cost.
    df = df.sort_index()
    # `astype("int64")` on a DatetimeIndex is UTC epoch nanos for BOTH naive and tz-aware
    # indexes — pandas stores aware timestamps as UTC internally and the zone is display only.
    # So this matches `_ts_to_epoch_ms` (naive read as UTC, aware converted) with no branch.
    # ⚠ An explicit `tz_convert("UTC")` branch was written here first and DELETED: mutating it
    # out left the tz test green, because there was never a case for it to handle. A branch
    # nothing can exercise is not defence, it is untested code.
    times = (df.index.astype("int64") // 1_000_000).tolist()
    rows = [
        {"time": t, "open": o, "high": h, "low": lo, "close": c}
        for t, o, h, lo, c in zip(
            times,
            df["open"].astype(float).tolist(),
            df["high"].astype(float).tolist(),
            df["low"].astype(float).tolist(),
            df["close"].astype(float).tolist(),
        )
    ]
    # Tick volume rides along when the feed has it, for the VWAP layer and nothing else. It is
    # STRIPPED again before the spec is written (`_strip_volume`) — see the note there.
    if "volume" in df.columns:
        for row, v in zip(rows, df["volume"].astype(float).tolist()):
            row["volume"] = v
    return rows


def _strip_volume(candles: list[dict]) -> None:
    """Drop `volume` from every candle, in place, once the server-side layers have read it.

    Volume is fetched for `vwap_overlays` and NOTHING in the browser plots it — the VWAP arrives
    as a computed series, not as bars to re-average. On a full-history run that is ~156k numbers
    of payload, parse time and heap bought for nobody, so the spec carries the line and not the
    ingredients. ⚠ `ChartCandle.volume` stays on the frontend contract as optional: the field is
    genuinely optional, and a chart that one day draws a volume pane should re-add it here
    deliberately rather than discover it arriving by accident.
    """
    for c in candles:
        c.pop("volume", None)


def _leg_label(reason: str) -> str:
    """A generic display label for a profit-take rung, from its exit-order id. `*-TP1/2/3` →
    `TP1/2/3`; anything else (a runner/trail/close) → `Exit`. Strategy-agnostic — the chart
    only ever shows TP1…TP3 / Exit, never a strategy's raw order names."""
    m = re.search(r"TP\s*([123])", (reason or "").upper())
    return f"TP{m.group(1)}" if m else "Exit"


def _trade_fib(p: dict, entry_price: float, mae_price: Optional[float]) -> Optional[dict]:
    """A stored trade's frozen fib leg → the chart's `fib` object, or None when it has none.

    The LEVELS are passed through untouched — they are the prices the strategy had in hand when
    it placed the order (see `backtest/output.py::_trade_fib`), and re-deriving them here from
    anchors would be a second implementation of the same fib on the same trade.

    What IS computed here is the pair of readings a level list cannot state on its own, and they
    are the thing that answers "what retracement did it go into":

      - `entryRatio`  — where the fill landed on this ladder (0.702 = it filled at the 70.2%
                        retrace). This is the trade's depth, stated in the strategy's own units.
      - `deepestRatio`— the same for the deepest ADVERSE price of the whole hold, i.e. how far the
                        retracement actually ran after the entry. It legitimately exceeds 1.0 on a
                        trade that traded through the leg origin.

    Both are pure geometry off two levels the ladder already carries, so no anchor, direction or
    range is needed and there is nothing here that can disagree with the strategy: a fib price is
    linear in its ratio, so any two (ratio, price) pairs define the whole line, and inverting it
    maps a price back to its ratio. Returns None for a degenerate ladder (a zero-height leg) —
    every ratio would map to the same price and a division would be by zero.
    """
    raw = p.get("fib")
    if not isinstance(raw, dict):
        return None
    levels = [
        {"ratio": float(r), "price": float(v)}
        for r, v in (lv for lv in (raw.get("levels") or []) if isinstance(lv, (list, tuple)) and len(lv) == 2)
        if isinstance(r, (int, float)) and isinstance(v, (int, float))
    ]
    if len(levels) < 2:
        return None
    lo, hi = levels[0], levels[-1]
    span_ratio = hi["ratio"] - lo["ratio"]
    span_price = hi["price"] - lo["price"]
    if not span_ratio or not span_price:
        return None

    def ratio_at(price: Optional[float]) -> Optional[float]:
        if price is None:
            return None
        return round(lo["ratio"] + (price - lo["price"]) * span_ratio / span_price, 4)

    out: dict = {"levels": levels, "entryRatio": ratio_at(entry_price)}
    start = raw.get("start_ms")
    if isinstance(start, (int, float)) and start:
        out["startTime"] = int(start)
    deepest = ratio_at(mae_price)
    if deepest is not None:
        out["deepestRatio"] = deepest
    return out


def _build_trades(equity_curve: list[dict], candles: list[dict]) -> list[dict]:
    """One trade per equity-curve point — every runner emits one point per CLOSED trade
    (NT8 `parse_trades_csv`, MT5 `_normalize_mt5_results`, Python `build_equity_curve`), so
    each point already carries the whole round trip: `entry_ms` (open), `date`/`exit_ms`
    (close), `direction`, `profit` (win/loss), `exit_name`, and — on Python runs — the exact
    `entry_price`/`exit_price` and `kind` (primary/secondary).

    Prices and the exit time come straight off the point when present; otherwise they fall
    back to the candle CLOSE at the trade's time (NT8/MT5 don't store fill prices, and older
    Python runs predate the extra fields). `pnl` drives the chart's green (win) / red (loss)
    box; `kind` lets it tell a primary trade from a 1m secondary re-entry.

    Profit-depth fields (`mfePrice`/`maePrice`/`profitLegs`/`stopPrice`) drive the chart's
    profit-depth trade view — how far price ran vs where each rung actually banked. They are
    OPTIONAL and only present on runs that carry them (Python runs today); a trade without them
    degrades to the plain entry→exit box. All generic — no strategy or runner names here.
    """
    times = [c["time"] for c in candles] if candles else []

    def price_at(epoch: Optional[int]) -> Optional[float]:
        if epoch is None or not candles:
            return None
        i = bisect.bisect_right(times, epoch) - 1
        if i < 0:
            i = 0
        return candles[i]["close"]

    trades: list[dict] = []
    n = 0
    for p in equity_curve:
        if not p.get("direction"):        # skip any opening-balance / no-direction point
            continue
        entry_ms = p.get("entry_ms")
        exit_ms = p.get("exit_ms")
        et = int(entry_ms) if entry_ms else _iso_to_epoch_ms(p.get("date", ""))
        xt = int(exit_ms) if exit_ms else _iso_to_epoch_ms(p.get("date", ""))
        if et is None or xt is None:
            continue
        ep = p.get("entry_price") or price_at(et)
        xp = p.get("exit_price") or price_at(xt)
        if ep is None or xp is None:
            continue
        direction = "short" if (p.get("direction") or "").strip().lower().startswith("s") else "long"
        n += 1
        # Profit-depth fields (optional; a real price is never 0, so `or None` == "absent").
        dir_sign = -1.0 if direction == "short" else 1.0
        mfe_price = p.get("mfe_price") or None
        mae_price = p.get("mae_price") or None
        stop_price = p.get("stop_price") or None
        # A rung BANKED profit only if it closed favorably beyond a scratch band (0.1R). A rung that
        # filled at the stop / breakeven (≈ entry) is not a profit-take and gets no green line —
        # this is what keeps a breakeven exit from being drawn as if it took profit.
        scratch = 0.1 * abs(ep - stop_price) if stop_price else 0.0
        profit_legs = [
            {"price": round(float(lg["price"]), 5), "label": _leg_label(str(lg.get("reason") or ""))}
            for lg in (p.get("legs") or [])
            if isinstance(lg.get("price"), (int, float))
            and (float(lg["price"]) - ep) * dir_sign > max(scratch, 1e-9)
        ]
        fib = _trade_fib(p, ep, mae_price)
        trades.append({
            "id": f"T{n}",
            "dir": direction,
            "entryTime": et,
            "entryPrice": ep,
            "exitTime": xt,
            "exitPrice": xp,
            "pnl": float(p.get("profit") or 0.0),
            "kind": p.get("kind") or "primary",
            "exitReason": p.get("exit_name") or "",
            "mfePrice": mfe_price,
            "maePrice": mae_price,
            "stopPrice": stop_price,
            "profitLegs": profit_legs,
            # TP TARGET ladder (nearest→furthest) — the chart draws the first UNHIT one faintly so a
            # runner's near-miss of the next TP is visible. Empty for a trade carrying no targets.
            "tpTargets": [
                round(float(t), 5) for t in (p.get("tp_targets") or [])
                if isinstance(t, (int, float)) and t
            ],
            # The fib LEG the trade was priced off, plus where the entry and the deepest adverse
            # price sat ON it. OPTIONAL: absent for any runner or strategy that doesn't record one
            # (NT8/MT5, older Python runs, the B-LEG fork), which is what makes the chart's Trade
            # fibs toggle disappear rather than render an empty layer.
            **({"fib": fib} if fib else {}),
        })
    return trades


def _build_blocks(run_dir: Path, candles: list[dict]) -> list[dict]:
    """The run's BLOCKED setups → the chart's `blocks` array.

    A blocked setup is a signal the strategy had ready and one of its own rules refused —
    it places no order, so it exists in no trade list, no equity curve, and no broker
    report. `blocked_setups.json` (written at run completion when the runner reports them)
    is the only source. Runners that don't report them have no file → `[]` → the chart's
    Blocked layer never appears, which is the honest answer for NT8/MT5.

    Clipped to the candle window for the same reason trades are: klinecharts clamps an
    out-of-range overlay onto the plot edge, which would pile every older marker up in the
    no-data region. Strategy-agnostic — every label and reason is a string the strategy
    wrote; this function knows nothing about what any of them mean, which is what lets the
    chart build its per-reason filters straight off the data.

    A setup can be refused by several rules at once, so `reasons` is a LIST (the strategy's
    own precedence order, primary first). A file written before that list existed carries a
    single `label`/`reason` pair instead, and is read as a one-item list — a run already on
    disk must never silently lose its markers because the record shape moved on.
    """
    path = run_dir / "blocked_setups.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
    except (ValueError, OSError):
        return []
    if not isinstance(raw, list) or not candles:
        return []
    lo, hi = candles[0]["time"], candles[-1]["time"]
    out: list[dict] = []
    for i, b in enumerate(raw, start=1):
        t = b.get("time_ms")
        if not isinstance(t, (int, float)) or not (lo <= t <= hi):
            continue
        raw_reasons = b.get("reasons")
        if not raw_reasons and b.get("label"):
            raw_reasons = [{"label": b.get("label"), "reason": b.get("reason")}]  # pre-list file
        reasons = [
            {"label": str(r.get("label") or "Blocked"), "reason": str(r.get("reason") or "")}
            for r in (raw_reasons or []) if isinstance(r, dict)
        ]
        if not reasons:
            continue        # a record naming no rule can't be filtered or explained — drop it
        out.append({
            "id": f"B{i}",
            "time": int(t),
            "dir": "short" if str(b.get("direction", "")).lower().startswith("s") else "long",
            "price": float(b.get("edge") or 0.0),
            "reasons": reasons,
        })
    return out


def _build_misses(run_dir: Path, candles: list[dict]) -> tuple[list[dict], list[str]]:
    """The run's MISSED setups → the chart's `misses` array, plus the reason labels the
    chart should start with HIDDEN.

    A miss is the block's companion: not "a ready trade a rule refused" but "a setup that got
    partway and died". Same plumbing, same optionality — `missed_setups.json` is the only
    source, so a runner that can't report them has no file, an empty list, and no toggle.

    **The second return value is the noise list, and it is DERIVED, not named.** A label goes on
    it when it never once appears on a `near` miss — i.e. the strategy itself never marked any
    setup carrying that reason as worth looking at. Nothing here knows what any label means; it
    reads the strategy's own `near` flag and hands the panel a list of strings to start with
    unticked. That is what reproduces the Pine's default view (`debug23Filter = "Near misses
    only"` plus `debugShow23Disarmed = false`) without the chart learning a single strategy
    concept — and one click restores the full set, which the Pine's radio buttons cannot do.
    """
    path = run_dir / "missed_setups.json"
    if not path.exists():
        return [], []
    try:
        raw = json.loads(path.read_text())
    except (ValueError, OSError):
        return [], []
    if not isinstance(raw, list) or not candles:
        return [], []
    lo, hi = candles[0]["time"], candles[-1]["time"]
    out: list[dict] = []
    near_labels: set[str] = set()
    all_labels: list[str] = []
    for i, m in enumerate(raw, start=1):
        t = m.get("time_ms")
        if not isinstance(t, (int, float)) or not (lo <= t <= hi):
            continue
        reasons = [
            {"label": str(r.get("label") or "Missed"), "reason": str(r.get("reason") or "")}
            for r in (m.get("reasons") or []) if isinstance(r, dict)
        ]
        if not reasons:
            continue    # a record naming nothing can't be filtered or explained — drop it
        is_near = bool(m.get("near", True))
        for r in reasons:
            if r["label"] not in all_labels:
                all_labels.append(r["label"])
            if is_near:
                near_labels.add(r["label"])
        out.append({
            "id": f"M{i}",
            "time": int(t),
            "dir": "short" if str(m.get("direction", "")).lower().startswith("s") else "long",
            "price": float(m.get("edge") or 0.0),
            "met": int(m.get("met") or 0),
            "of": int(m.get("of") or 0),
            "near": is_near,
            "metLines": [str(s) for s in (m.get("met_lines") or [])],
            "reasons": reasons,
        })
    return out, [lb for lb in all_labels if lb not in near_labels]


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
    all_days = sorted({(c["time"] // _DAY_MS) * _DAY_MS for c in m15})
    for day in all_days:
        a0, a1, t_flat = day + a_start, day + a_end, day + flat
        lo_i = bisect.bisect_left(m15_times, a0)
        hi_i = bisect.bisect_left(m15_times, a1)
        window = m15[lo_i:hi_i]
        if not window:
            continue
        hi = max(c["high"] for c in window)
        low = min(c["low"] for c in window)
        overlays.append({
            "type": "box", "group": "ORB Range", "t0": a0, "t1": a1,
            "top": hi, "bottom": low, "style": {"color": "#2dd4bf", "fillColor": "rgba(45,212,191,0.20)", "lineStyle": "dashed"},
        })
        atr = atr_before(day)
        if atr:
            overlays.append({
                "type": "hline", "group": "ORB Range", "t0": a1, "t1": t_flat,
                "price": round(hi + buffer_atr * atr, 5),
                "style": {"color": "#33ff99", "lineStyle": "dashed"},
            })
            overlays.append({
                "type": "hline", "group": "ORB Range", "t0": a1, "t1": t_flat,
                "price": round(low - buffer_atr * atr, 5),
                "style": {"color": "#ff6680", "lineStyle": "dashed"},
            })

    indicators = [{
        "name": f"ATR({period}) D1", "params": {"period": period},
        "pane": "sub", "series": atr_series,
    }] if atr_series else []
    return overlays, indicators


def cached_chart_spec_bytes(run_id: str) -> Optional[bytes]:
    """The cached ChartSpec as the JSON BYTES on disk, or None if there is no usable cache.

    🔴 **The router used to `json.loads` this file and hand the dict back to FastAPI, which
    immediately `json.dumps`ed it again — 0.26s of the endpoint's 0.40s spent turning 4 MB of JSON
    into Python objects nothing looked at.** MEASURED on run `997c14cc53bc`'s real 4,029,681-byte
    cache: read 0.003s, `json.loads` 0.089s, `json.dumps` 0.171s. Serving the bytes skips both, and
    the saving SCALES with the spec — which is what makes shipping a whole run's history viable
    rather than merely smaller.

    ⚠ **This is only safe because `_write_spec_cache` is ATOMIC.** Serving bytes means nothing
    parses them, so a half-written file would reach the browser as a JSON syntax error instead of
    being caught and rebuilt the way `build_chart_spec`'s own `except ValueError` catches it. The
    cheap shape check below is a backstop for a cache written by an older build, not the guarantee.
    """
    path = LAB_RESULTS_DIR / run_id / "chart_spec.json"
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    trimmed = raw.strip()
    # Not a parse — a parse is the entire cost this function exists to avoid. It only rejects the
    # torn-write shape, which is the one an atomic write has already made impossible.
    if not trimmed.startswith(b"{") or not trimmed.endswith(b"}"):
        return None
    return raw


def _write_spec_cache(spec_path: Path, spec: dict) -> None:
    """Write the spec cache atomically — tmp file then `os.replace`, the same rule `progress.json`
    follows. A plain `write_text` leaves a readable, truncated file if the process dies mid-write,
    and `cached_chart_spec_bytes` serves bytes without parsing them, so a torn cache would be
    served to the browser rather than rebuilt."""
    # `separators` is not cosmetic now that these bytes ARE the response: plain `json.dumps` writes
    # ", " and ": ", and on this spec that whitespace is 418 KB (4,029,681 vs 3,611,888 bytes,
    # measured) of pure padding shipped to the browser. It is also what FastAPI's own JSONResponse
    # uses, so the cached and freshly-built responses stay byte-identical.
    tmp = spec_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(spec, separators=(",", ":")))
    os.replace(tmp, spec_path)


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
    # NT8 only has daily bars today; MT5 ideally has intraday from the agent, and a Python run has
    # intraday in the backtest cache it replayed.
    #
    # The chart ALWAYS ships the timeframe the run TRADED — it is the only one its trades and blocked
    # setups line up with, so a coarser view can cover the whole span and still be useless for the one
    # job this chart has.
    #
    # 🟢 **It now ships the WHOLE RUN, and `_capped_start` is retired (2026-08-06).** The window was
    # trimmed to the newest `_CANDLE_CAP` bars because a 6.5-year M15 spec was ~15 MB and the endpoint
    # took the better part of a second; everything older was reached by PAGING it in on scroll-left.
    # Three measurements retire that design:
    #
    #   1. **Paging is 7x more expensive than building it once.** A page costs ~7.2s of analysis
    #      replay and a deep jump takes ~14 of them — MEASURED at 90.3s in a real browser — against
    #      **17.8s for one full-history build**, which is then cached and served in **0.004s** for
    #      ever after (see `cached_chart_spec_bytes`).
    #   2. **The payload was never the expensive half.** Serving the cached bytes made a 4 MB spec a
    #      4 ms response; the full-history one is 14.4 MB and parses in ~151 ms in the browser, once.
    #   3. **Candles are nearly free to hold.** MEASURED: 155,776 of them are 40 MB of browser heap
    #      and scroll and zoom unaffected. The chart's real budget is OVERLAY COUNT, which is
    #      superlinear — and the panel now creates overlays for the VIEWPORT rather than for the
    #      loaded history, so shipping more bars no longer costs anything to draw.
    #
    # ⚠ The reader's own reach is what this buys: a jump to any date is now a scroll, not a wait.
    intraday = runner in ("mt5", "python")
    base_tf = _base_timeframe(row.get("bar_type"), row.get("bar_value")) if intraday else "D1"
    ship_from = row["start_date"]

    candles = _build_candles(instrument, ship_from, row["end_date"], base_tf, runner)
    # Fallback: the MT5 agent can't always serve intraday history (symbol not selected, or the
    # run's sub-hour TF unsupported). Daily bars come from yfinance via the D1 path — coarse, but
    # a real price chart beats none. baseTimeframe reflects what actually loaded.
    # Python is deliberately excluded: its bars come from the cache the run itself replayed, so a
    # fallback to a different feed would silently draw a chart the run never traded.
    if not candles and base_tf != "D1" and runner != "python":
        candles = _build_candles(instrument, row["start_date"], row["end_date"], "D1", runner)
        if candles:
            base_tf, ship_from = "D1", row["start_date"]

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

    # Market-structure overlays (BOS/CHoCH/swings) from the CANONICAL engine, computed on the
    # displayed candles. Generic — runs for every run that has candles, tagged into the four
    # structure Layers groups (default OFF in the panel). Best-effort: [] on any failure.
    overlays = overlays + build_market_structure_overlays(candles)

    blocks = _build_blocks(run_dir, candles)
    misses, miss_noise = _build_misses(run_dir, candles)

    # Fair value gaps — but ONLY the ones that were live when something happened. The anchors are
    # every trade ENTRY, every blocked setup and every missed setup, so the layer answers "where were
    # the gaps when this fired?" rather than papering the chart with every gap the run ever saw. The
    # gaps themselves are mpc_assistant.pine's (see fvg_overlays.py — the strategy runs a different,
    # stricter set). Best-effort: [] on any failure, and [] when the run has no trades/blocks/misses
    # in the window, which is what keeps the toggle off an NT8/MT5 chart.
    anchors = (
        [t["entryTime"] for t in trades] + [b["time"] for b in blocks] + [m["time"] for m in misses]
    )
    overlays = overlays + build_fvg_overlays(candles, anchors, base_tf)

    # Order blocks — the same anchor rule, for the same reason, off the canonical OB engine (see
    # ob_overlays.py). Measured on run `75ccc776d10c`: 2,567 blocks created over the window, 579 of
    # them live when something fired. Unlike the gaps there is no settings fork to warn about — the
    # strategy files dropped order blocks entirely in 2026-07, so mpc_assistant.pine is the only
    # source; equally, a drawn block never explains an entry, because the bot reads none.
    overlays = overlays + build_ob_overlays(candles, anchors)

    # Session VWAP — a main-pane line off the canonical engine, default OFF. It is the one layer
    # here that needs the bar's VOLUME, so it returns None (no toggle) whenever the run's bars
    # carry none; see vwap_overlays.py for why a missing volume is a refusal rather than a zero.
    vwap = build_vwap_indicator(candles)
    if vwap:
        indicators = indicators + [vwap]
    # Every server-side layer that wanted volume has now read it. The browser plots none, so it
    # does not travel — ~156k numbers of payload and parse bought for nobody.
    _strip_volume(candles)

    spec = {
        "instrument": instrument,
        "baseTimeframe": base_tf,
        # Same thing now that the window is what gets capped, not the bars — kept so a frontend or a
        # cached spec that reads either name gets the same answer.
        "runTimeframe": base_tf,
        # How far back the run goes. The shipped candles start at `ship_from`, which is later than
        # this on a long run; the panel pages the gap in as you scroll left, and stops here.
        "historyStartMs": _iso_to_epoch_ms(row["start_date"]),
        "brokerGmtOffsetHours": 0,
        "candles": candles,
        "sessions": [dict(s) for s in _FX_SESSIONS],
        "trades": trades,
        "blocks": blocks,
        "misses": misses,
        # Reason labels the panel starts with unticked — derived from the strategy's own `near`
        # flag, never named here. See `_build_misses`.
        "missNoise": miss_noise,
        "overlays": overlays,
        "indicators": indicators,
    }

    run_dir.mkdir(parents=True, exist_ok=True)
    _write_spec_cache(spec_path, spec)
    log.info("chart_spec: built for %s — %d candles, %d trades, %d overlays, %d indicators (%s)",
             run_id, len(candles), len(trades), len(overlays), len(indicators), base_tf)
    return spec


def build_stack_chart_spec(stack_id: str) -> Optional[dict]:
    """Build a MERGED ChartSpec for a portfolio stack — one shared candle chart carrying every
    completed leg's trades, each tagged with `layer` = its strategy_id so the frontend can filter
    by the SAME per-strategy toggle it uses for the equity chart (and colour each layer to match).

    Reuses each leg's own `build_chart_spec` (all legs share one instrument/TF/window, so the
    candles are identical) and drops the per-strategy structure overlays/indicators — a portfolio
    price view stays readable with trades only. Blocked AND missed setups are dropped for a second
    reason: neither carries a `layer`, so on a merged chart there would be no way to tell WHOSE
    rule refused a setup or WHOSE confluence was missing. Omitting the keys hides both toggles; a
    leg's own page still has them. Returns
    None if the stack is unknown; a spec with
    empty candles if no leg produced any (frontend shows "no price data"). Not cached (legs can
    complete incrementally); each leg's own spec is cached, so the merge is cheap."""
    rows = lab_db.list_stack_runs(stack_id)
    if not rows:
        return None

    first_spec: Optional[dict] = None
    base_spec: Optional[dict] = None      # first leg that actually has candles
    base_run_id: Optional[str] = None     # its run_id — drives the price chart's drill-down/fullscreen
    all_trades: list[dict] = []
    layers: list[dict] = []
    for r in rows:
        if r["status"] != "complete":
            continue
        spec = build_chart_spec(r["run_id"])
        if not spec:
            continue
        first_spec = first_spec or spec
        if base_spec is None and spec.get("candles"):
            base_spec = spec
            base_run_id = r["run_id"]
        layers.append({
            "strategy_id": r["strategy_id"],
            "strategy_name": r.get("strategy_name", ""),
            "run_id": r["run_id"],
        })
        for tr in spec.get("trades", []):
            t = dict(tr)
            t["layer"] = r["strategy_id"]
            t["id"] = f"{r['strategy_id']}:{tr.get('id', '')}"  # unique across layers
            all_trades.append(t)

    src = base_spec or first_spec
    if src is None:
        return None

    all_trades.sort(key=lambda t: t.get("entryTime", 0))
    return {
        "instrument": src["instrument"],
        "baseTimeframe": src["baseTimeframe"],
        "runTimeframe": src.get("runTimeframe", src["baseTimeframe"]),
        "historyStartMs": src.get("historyStartMs"),
        "brokerGmtOffsetHours": src["brokerGmtOffsetHours"],
        "candles": src["candles"],
        "sessions": [dict(s) for s in src.get("sessions", [])],
        "trades": all_trades,
        # Structure overlays + indicators are a property of the MARKET on these candles, not of
        # any one strategy — identical for every leg (same instrument/timeframe/window). So the
        # stack's price chart carries the base leg's, giving it full BacktestDetail parity
        # (structure layers, ATR pane, fib/measurement tools all read the same spec).
        # The two ANCHORED groups — fair value gaps and order blocks — are the exception, dropped
        # for the same reason blocks and misses are: both are anchored to the BASE leg's trades, so
        # on a merged chart they would draw zones at one strategy's entries and nothing at the
        # others' — which reads as "these setups had gaps and those didn't" rather than "only one
        # leg was measured". A leg's own page still carries both.
        "overlays": [dict(o) for o in src.get("overlays", [])
                     if o.get("group") not in (GROUP_FVG, GROUP_OB)],
        "indicators": [dict(i) for i in src.get("indicators", [])],
        "layers": layers,
        # The base leg's run_id — the frontend routes M1/M5 drill-down + fullscreen candle fetches
        # through it (all legs share the same feed, so any leg's candles are the stack's candles).
        "base_run_id": base_run_id or (rows[0]["run_id"] if rows else None),
    }


def build_run_candles(
    run_id: str, timeframe: str, from_ms: int, to_ms: int,
) -> Optional[dict]:
    """Candles for a bounded [from_ms, to_ms] window of a run at an ARBITRARY timeframe — the
    DRILL-DOWN data path (e.g. 1m under a 15m run, to see a trade's exact entry).

    Reuses the run's OWN feed + runner (`get_ohlc` via `_build_candles`), so a zoom shows the
    same bars the run traded, never a different feed. Not cached — it is a live, per-window pull.

    ⚠ **This used to serve the chart's scroll-left PAGING path as well, with an `analysis=True`
    branch returning that window's structure overlays / gaps / blocked / missed setups
    (`_page_analysis`, deleted 2026-08-06).** The spec now carries the whole run and every window's
    analysis with it, so the panel pages from memory and nothing calls back for a window. Do not
    re-add a per-window analysis branch here: it replayed the engines over a 2,000-bar warm-up on
    every page, which measured ~7.2s a page against 17.8s to build the entire run once.

    Returns:
      - None if the run is unknown (router → 404).
      - {instrument, timeframe, candles, available, data_start_ms, hard_edge} otherwise.
        `available` is False (candles empty) when the feed can't serve that window at all — most
        often the MT5 agent being offline. `hard_edge` is True when the oldest bar returned is the
        broker's TRUE data limit (the feed has nothing older), with `data_start_ms` marking it —
        the frontend draws its red "no earlier data" line there. It is False when the feed simply
        has more than our fetch clamp could ship (then the edge is ours, not the broker's).
    """
    row = lab_db.get_run(run_id)
    if not row:
        return None
    runner = row.get("runner") or "ninjatrader"
    instrument = row["instrument"]

    if from_ms > to_ms:
        from_ms, to_ms = to_ms, from_ms
    # Guard the fetch volume: clamp the span to the newest slice that stays under the DRILL cap for
    # this timeframe (a floor so a pathological request can't pull years of 1m). Keeps the most-recent
    # edge. The cap sits above the broker's real M1/M5 depth, so for a normal drill-down it never
    # binds — which is what keeps `hard_edge` honest (a clipped request could fake a boundary).
    tf_min = _TF_MIN.get(timeframe.upper(), 15)
    max_span_ms = int(_DRILL_CANDLE_CAP * tf_min * 60_000 / (5 / 7))  # ~forex: 5 trading days/week
    clamped = (to_ms - from_ms) > max_span_ms
    if clamped:
        from_ms = to_ms - max_span_ms

    # The fetch is day-granular; widen to whole UTC days, then slice back to the exact window.
    start_date = datetime.fromtimestamp(from_ms / 1000, tz=timezone.utc).date().isoformat()
    end_date = datetime.fromtimestamp(to_ms / 1000, tz=timezone.utc).date().isoformat()
    candles = _build_candles(instrument, start_date, end_date, timeframe, runner)
    candles = [c for c in candles if from_ms <= c["time"] <= to_ms]
    # Drill-down is bars only — no layer is rebuilt here, so nothing reads the volume and it must
    # not travel. The spec's own builder strips it for the same reason.
    _strip_volume(candles)
    data_start_ms = candles[0]["time"] if candles else None
    # True broker limit ⇔ data exists, its oldest bar is well past what we asked for (beyond a
    # weekend/holiday gap), and OUR cap didn't clip the request.
    hard_edge = bool(candles) and not clamped and (data_start_ms - from_ms) > _HARD_EDGE_SLOP_MS
    out = {
        "instrument": instrument,
        "timeframe": timeframe.upper(),
        "candles": candles,
        "available": bool(candles),
        "data_start_ms": data_start_ms,
        "hard_edge": hard_edge,
    }
    log.info("run_candles: %s %s [%s, %s] -> %d candles (hard_edge=%s)",
             run_id, timeframe, start_date, end_date, len(candles), hard_edge)
    return out
