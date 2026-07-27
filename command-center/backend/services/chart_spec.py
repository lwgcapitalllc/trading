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
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from services import lab_db, ohlc_fetcher
from services.backtest_runner import LAB_RESULTS_DIR
from services.structure_overlays import build_market_structure_overlays

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
_TF_LADDER = ["M5", "M15", "M30", "H1", "H4", "D1"]
_CANDLE_CAP = 35_000  # keeps ~1yr at M15; a 5yr run steps up to H1 instead of ~125k M15 candles
# Drill-down loads the broker's FULL sub-base depth in one shot (M5's ~240d ≈ 49k candles). It sits
# ABOVE the base-chart cap on purpose: the render cap must never be the binding limit for a drill-down,
# so the ONLY left edge the user hits is the broker's real data boundary (the red "no earlier data"
# line), never our own clip.
_DRILL_CANDLE_CAP = 60_000
# A left edge shorter than what was requested is the broker's TRUE limit only when the gap exceeds a
# long weekend / holiday (bars are absent then too, but that isn't a data boundary).
_HARD_EDGE_SLOP_MS = 4 * 24 * 60 * 60 * 1000


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


def _leg_label(reason: str) -> str:
    """A generic display label for a profit-take rung, from its exit-order id. `*-TP1/2/3` →
    `TP1/2/3`; anything else (a runner/trail/close) → `Exit`. Strategy-agnostic — the chart
    only ever shows TP1…TP3 / Exit, never a strategy's raw order names."""
    m = re.search(r"TP\s*([123])", (reason or "").upper())
    return f"TP{m.group(1)}" if m else "Exit"


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
    own precedence order, primary first).
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
        reasons = [
            {"label": str(r.get("label") or "Blocked"), "reason": str(r.get("reason") or "")}
            for r in (b.get("reasons") or []) if isinstance(r, dict)
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
    # NT8 only has daily bars today; MT5 ideally has intraday from the agent, and a Python run
    # has intraday in the backtest cache it replayed. Cap the candle volume by stepping the TF up
    # for long spans (a 5yr run → H1, not ~125k M15 candles).
    intraday = runner in ("mt5", "python")
    base_tf = _base_timeframe(row.get("bar_type"), row.get("bar_value")) if intraday else "D1"
    if intraday:
        base_tf = _fit_timeframe(base_tf, row["start_date"], row["end_date"])

    candles = _build_candles(instrument, row["start_date"], row["end_date"], base_tf, runner)
    # Fallback: the MT5 agent can't always serve intraday history (symbol not selected, or the
    # run's sub-hour TF unsupported). Daily bars come from yfinance via the D1 path — coarse, but
    # a real price chart beats none. baseTimeframe reflects what actually loaded.
    # Python is deliberately excluded: its bars come from the cache the run itself replayed, so a
    # fallback to a different feed would silently draw a chart the run never traded.
    if not candles and base_tf != "D1" and runner != "python":
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

    # Market-structure overlays (BOS/CHoCH/swings) from the CANONICAL engine, computed on the
    # displayed candles. Generic — runs for every run that has candles, tagged into the four
    # structure Layers groups (default OFF in the panel). Best-effort: [] on any failure.
    overlays = overlays + build_market_structure_overlays(candles)

    spec = {
        "instrument": instrument,
        "baseTimeframe": base_tf,
        "brokerGmtOffsetHours": 0,
        "candles": candles,
        "sessions": [dict(s) for s in _FX_SESSIONS],
        "trades": trades,
        "blocks": _build_blocks(run_dir, candles),
        "overlays": overlays,
        "indicators": indicators,
    }

    run_dir.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec))
    log.info("chart_spec: built for %s — %d candles, %d trades, %d overlays, %d indicators (%s)",
             run_id, len(candles), len(trades), len(overlays), len(indicators), base_tf)
    return spec


def build_stack_chart_spec(stack_id: str) -> Optional[dict]:
    """Build a MERGED ChartSpec for a portfolio stack — one shared candle chart carrying every
    completed leg's trades, each tagged with `layer` = its strategy_id so the frontend can filter
    by the SAME per-strategy toggle it uses for the equity chart (and colour each layer to match).

    Reuses each leg's own `build_chart_spec` (all legs share one instrument/TF/window, so the
    candles are identical) and drops the per-strategy structure overlays/indicators — a portfolio
    price view stays readable with trades only. Blocked setups are dropped for a second reason:
    they carry no `layer`, so on a merged chart there would be no way to tell WHOSE rule refused
    a setup. Omitting the key hides the Blocked toggle; a leg's own page still has it. Returns
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
        "brokerGmtOffsetHours": src["brokerGmtOffsetHours"],
        "candles": src["candles"],
        "sessions": [dict(s) for s in src.get("sessions", [])],
        "trades": all_trades,
        # Structure overlays + indicators are a property of the MARKET on these candles, not of
        # any one strategy — identical for every leg (same instrument/timeframe/window). So the
        # stack's price chart carries the base leg's, giving it full BacktestDetail parity
        # (structure layers, ATR pane, fib/measurement tools all read the same spec).
        "overlays": [dict(o) for o in src.get("overlays", [])],
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
    drill-down data path (e.g. 1m under a 15m run, to see a trade's exact entry).

    Reuses the run's OWN feed + runner (`get_ohlc` via `_build_candles`), so a zoom shows the
    same bars the run traded, never a different feed. Not cached — it is a live, per-window pull.

    Returns:
      - None if the run is unknown (router → 404).
      - {instrument, timeframe, candles, available, data_start_ms, hard_edge} otherwise. `available`
        is False (candles empty) when the feed can't serve that window at all — most often the MT5
        agent being offline. `hard_edge` is True when the oldest bar returned is the broker's TRUE
        data limit (the feed has nothing older), with `data_start_ms` marking it — the frontend
        draws its red "no earlier data" line there. It is False when the feed simply has more than
        our render cap could ship (then the edge is ours, not the broker's — no line).
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
    data_start_ms = candles[0]["time"] if candles else None
    # True broker limit ⇔ data exists, its oldest bar is well past what we asked for (beyond a
    # weekend/holiday gap), and OUR cap didn't clip the request.
    hard_edge = bool(candles) and not clamped and (data_start_ms - from_ms) > _HARD_EDGE_SLOP_MS
    log.info("run_candles: %s %s [%s, %s] -> %d candles (hard_edge=%s)",
             run_id, timeframe, start_date, end_date, len(candles), hard_edge)
    return {
        "instrument": instrument,
        "timeframe": timeframe.upper(),
        "candles": candles,
        "available": bool(candles),
        "data_start_ms": data_start_ms,
        "hard_edge": hard_edge,
    }
