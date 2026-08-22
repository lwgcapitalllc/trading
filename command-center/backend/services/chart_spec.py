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
from typing import Any, Optional

from services import history_limits, lab_db, metrics, ohlc_fetcher
from services.backtest_runner import LAB_RESULTS_DIR
from services.candle_overlays import GROUP_CANDLES, build_candle_overlays
from services.fvg_overlays import GROUP_FVG, build_fvg_overlays
from services.liquidity_overlays import GROUPS as GROUPS_LIQ
from services.liquidity_overlays import build_liquidity_overlays
from services.ob_overlays import GROUP_OB, build_ob_overlays
from services.structure_overlays import (
    GROUP_INTERNAL,
    GROUP_INTERNAL_HISTORIC,
    build_market_structure_overlays,
)
from services.vwap_overlays import build_vwap_indicator

log = logging.getLogger("CHARTSPEC")

# Market sessions — data, not strategy logic. Times are local to each `tz`, which is what makes them
# DST-aware: a window stated in its own city's clock does not move when that city changes its clocks,
# while its UTC span does. Read on a UTC-4 chart, London and New York therefore shift an hour twice a
# year and Tokyo never does.
#
# 🔴 **THESE ARE `mpc_assistant.pine`'s WINDOWS AND THEY WERE NOT (fixed 2026-08-08).** Tokyo ended at
# 15:00 and London at 16:30 here, against the indicator's 18:00 and 17:00 — so two of the three boxes
# on a backtest chart were SHORTER than the boxes on the TradingView chart the run is read against,
# and nothing on either screen said so. Aaron confirmed the indicator is the correct source.
# ⚠ **The engines already agreed with the indicator and this file was the only dissenter** —
# `engines/sessions/engine.py`'s `SessionEngine` defaults are `Asia 0900-1800 Asia/Tokyo`,
# `London 0800-1700 Europe/London`, `NY 0800-1700 America/New_York`, re-synced from the 2026-07-31
# mpc paste. So this was a THIRD statement of a fact two other places already held, which is this
# repo's most-repeated defect; it is now the same three windows.
# ⚠ **The engine's names are `Asia`/`London`/`NY` and the display names below stay `Tokyo`/`London`/
# `New York` deliberately.** The panel keys its per-session toggle state on `name`, so renaming would
# reset a reader's switches, and these are the labels on the chart legend rather than an identifier
# anything resolves through.
_FX_SESSIONS = [
    {"name": "Tokyo", "tz": "Asia/Tokyo", "start": "09:00", "end": "18:00", "color": "#f472b6"},
    {"name": "London", "tz": "Europe/London", "start": "08:00", "end": "17:00", "color": "#60a5fa"},
    {
        "name": "New York",
        "tz": "America/New_York",
        "start": "08:00",
        "end": "17:00",
        "color": "#fb923c",
    },
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

# Bars of context replayed IN FRONT of a drill-down window before its structure is read off.
# The structure engine is a streaming state machine, so a cold replay opens with no swings and no
# active levels — i.e. the first stretch of every drill-down would be blank and then "catch up",
# which reads as the layer being broken rather than as the engine warming.
_DRILL_WARMUP_BARS = 2_000


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


def _build_candles(
    instrument: str, start_date: str, end_date: str, base_tf: str, runner: str
) -> list[dict]:
    """Candle rows for a window, or `[]`. The spec build's view — it degrades to an empty chart
    either way, so it does not need to know WHY."""
    return _fetch_candles(instrument, start_date, end_date, base_tf, runner)[0]


def _fetch_candles(
    instrument: str,
    start_date: str,
    end_date: str,
    base_tf: str,
    runner: str,
) -> tuple[list[dict], Optional[str]]:
    """`(rows, error)` — and the error half is the point.

    🔴 **Until 2026-08-07 this swallowed the exception and returned `[]`, so "the MT5 agent is down"
    and "the broker has no bars that far back" were THE SAME VALUE.** `build_run_candles` then set
    `available = bool(candles)`, which is tautological, while its own docstring claimed `available:
    false` meant the feed could not serve the window. The distinction was destroyed here and
    unrecoverable above, so the price chart's drill-down could only hedge — it printed *"no data
    here (feed offline, or none this far back?)"*, asking the reader a question the fetch had
    already answered. Same rule as `mt5_link`, three layers down: never let "no" and "cannot ask"
    be the same value.
    """
    # ohlc_fetcher normalizes the symbol (strips the broker suffix, re-adds a configured one), so
    # we can pass the run instrument as-is — the MT5 agent's terminal uses plain names.
    try:
        df = ohlc_fetcher.get_ohlc(
            instrument, start_date, end_date, timeframe=base_tf, runner=runner
        )
    except Exception as exc:  # noqa: BLE001 — fetch is best-effort; empty candles degrade gracefully
        log.warning("chart_spec: candle fetch failed for %s %s: %s", instrument, base_tf, exc)
        return [], f"{type(exc).__name__}: {exc}"[:200]
    if df is None or df.empty:
        # The feed ANSWERED and had nothing for this window — a real fact about the broker's depth,
        # not a failure. `None` error is what lets the caller say so.
        return [], None
    # Column-at-a-time, NOT `df.iterrows()`. Measured 2026-08-06 on a real 155,776-bar run:
    # 12.63s by iterrows against 0.15s here, byte-identical output — 85x, paid on every chart
    # request. `iterrows` builds a fresh Series per row, which is the whole cost.
    df = df.sort_index()
    # `astype("int64")` on a DatetimeIndex is UTC epoch in the index's OWN UNIT for both naive and
    # tz-aware indexes — pandas stores aware timestamps as UTC internally and the zone is display
    # only. So this matches `_ts_to_epoch_ms` (naive read as UTC, aware converted) with no branch.
    # ⚠ An explicit `tz_convert("UTC")` branch was written here first and DELETED: mutating it
    # out left the tz test green, because there was never a case for it to handle. A branch
    # nothing can exercise is not defence, it is untested code.
    #
    # ⚠ **THE UNIT MUST BE STATED, AND IT WAS NOT UNTIL 2026-08-08: this read `astype("int64") //
    # 1_000_000`, i.e. nanos-to-millis, on an index whose unit pandas chooses.** Nanoseconds was
    # the only resolution pandas 1.x had and is still the default in pandas 2 — so the old divide
    # is CORRECT on this venv (2.3.3) and nothing served from it was ever wrong. **pandas 3 makes
    # MICROseconds the default for parsed timestamps**, and the same divide then yields epoch
    # SECONDS wearing the name `_ms` — every candle timestamp 1000x too small, silently, in a field
    # every consumer reads as ms. MEASURED on pandas 3.0.5: `2026-08-05 00:00` comes back as
    # `1785888000` instead of `1785888000000`.
    #
    # So this is a LATENT bug that fires on the day this venv upgrades, not a live one — recorded
    # as latent because the pin is what makes it latent, and a pin is not a fix. `as_unit("ms")`
    # states the unit instead of assuming it and is byte-identical under pandas 2, so the answer
    # stops depending on how pandas happened to parse the cache file.
    times = df.index.as_unit("ms").astype("int64").tolist()
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
    # Tick volume rides along when the feed has it — read server-side by the VWAP layer, and shipped
    # so the chart's own OHLC readout can print it. ABSENT rather than zero when the feed supplied
    # none (a bar cache written before 2026-08-06, or a runner whose feed carries no volume), because
    # klinecharts renders a missing value as `n/a` and a fabricated 0 as a dead session.
    if "volume" in df.columns:
        for row, v in zip(rows, df["volume"].astype(float).tolist()):
            row["volume"] = v
    return rows, None


def _leg_label(reason: str, price: float, dir_sign: float, targets: list) -> str:
    """A generic display label for a profit-take rung, from its exit-order id and where it
    actually closed. `*-TP1/2/3` → `TP1/2/3`; anything else (a runner/trail/close) → `Exit`.
    Strategy-agnostic — the chart only ever shows TP1…TP3 / Exit, never a strategy's raw
    order names.

    🔴 The order id alone is NOT enough, and reading it alone put two `TP1` chips at two
    different prices on one trade (run 687c8df2a523, the re-entry short of 2026-05-21). A
    rung keeps its order id when something ELSE closes it — a trail, a time stop, a flip —
    so an order named for the first target routinely comes off nowhere near that target.
    That trade banked half at 4,507.04 on the trail while its first target sat at 4,491.99,
    and the chart drew a green `TP1` at each, one of them claiming a target hit that never
    happened.

    So the id is treated as a CLAIM and checked against the rung it names: a leg that did not
    reach its own target price did not fill there, whatever it is called, and is labelled
    `Exit`. A better-than-target fill still counts — a limit that gaps fills past its price.
    A rung the trade reports no target for cannot be checked, so its id stands: absent
    evidence is not evidence against.
    """
    m = re.search(r"TP\s*([123])", (reason or "").upper())
    if not m:
        return "Exit"
    i = int(m.group(1)) - 1
    target = targets[i]["price"] if i < len(targets) else None
    if target is not None and (price - target) * dir_sign < -1e-9:
        return "Exit"
    return f"TP{m.group(1)}"


def _tp_targets(raw: Any) -> list:
    """A stored trade's `tp_targets` → the chart's rung list, one `{price, banks?}` each.

    Accepts both shapes `backtest/output.py::_tp_targets` emits, and the distinction is the
    whole reason this function exists: `banks` present says the strategy REPORTED whether the
    rung places an order, and `banks` absent says nobody asked. A rung with no order is not a
    profit target — nothing is ever sold there and touching it only steps the stop — so the
    chart must not draw it with a target's name. **A missing `banks` must never be read as
    `False`**: every run stored before 2026-08-21 carries bare prices, and defaulting those to
    "banks nothing" would relabel every target on every historical chart off a measurement that
    was never made.
    """
    out = []
    for t in raw or []:
        if isinstance(t, bool):
            continue
        if isinstance(t, (int, float)):
            if t:
                out.append({"price": round(float(t), 5)})
        elif isinstance(t, dict) and isinstance(t.get("price"), (int, float)) and t["price"]:
            rung = {"price": round(float(t["price"]), 5)}
            if isinstance(t.get("banks"), bool):
                rung["banks"] = t["banks"]
            out.append(rung)
    return out


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
        for r, v in (
            lv for lv in (raw.get("levels") or []) if isinstance(lv, (list, tuple)) and len(lv) == 2
        )
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

    # WON / SCRATCH / LOST per trade, graded against the run's own median full loss — the same bar
    # `scratch_count` reports on the KPI row. None when the run has no loss to scale against; the
    # chart then falls back to the sign of `pnl`, which is the honest degradation (an ungraded
    # trade must not be drawn as a measured flat one).
    outcomes = metrics.trade_outcomes(equity_curve)

    trades: list[dict] = []
    n = 0
    for i, p in enumerate(equity_curve):
        if not p.get("direction"):  # skip any opening-balance / no-direction point
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
        direction = (
            "short" if (p.get("direction") or "").strip().lower().startswith("s") else "long"
        )
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
        tp_targets = _tp_targets(p.get("tp_targets"))
        # Two rungs closed by the SAME event land at the same price with the same label — a
        # trail taking the whole position gives one leg per still-open bracket, all at one
        # price. They are one line on the chart, so they are one chip: drawing the second
        # stacks a duplicate 15px below and reads as two separate fills.
        profit_legs: list = []
        for lg in p.get("legs") or []:
            if not isinstance(lg.get("price"), (int, float)):
                continue
            lp = float(lg["price"])
            if (lp - ep) * dir_sign <= max(scratch, 1e-9):
                continue
            leg = {
                "price": round(lp, 5),
                "label": _leg_label(str(lg.get("reason") or ""), lp, dir_sign, tp_targets),
            }
            if leg not in profit_legs:
                profit_legs.append(leg)
        fib = _trade_fib(p, ep, mae_price)
        trades.append(
            {
                "id": f"T{n}",
                "dir": direction,
                "entryTime": et,
                "entryPrice": ep,
                "exitTime": xt,
                "exitPrice": xp,
                "pnl": float(p.get("profit") or 0.0),
                # The graded verdict, when the run could be graded. It is a THIRD state and not a
                # nicer word for a small loss: `pnl > 0` alone calls a trade that netted exactly
                # $0.00 a LOSS, which is what a scale-in add that hands the locked profit back
                # produces (run 295a6ff29d21, 8 trades).
                **({"outcome": outcomes[i]} if outcomes else {}),
                "kind": p.get("kind") or "primary",
                # For a re-entry, what the trade it FOLLOWED did. The chart draws a different tag
                # for a re-entry after a scratch and one after a stop-out, because they are
                # different situations and one `SEC` cannot say which. ⚠ Emitted only when the run
                # recorded it — absent means "cannot tell", and the chart falls back to the plain
                # book tag rather than picking one. Generic: no strategy names it.
                **({"after": p["after"]} if isinstance(p.get("after"), str) and p["after"] else {}),
                "exitReason": p.get("exit_name") or "",
                "mfePrice": mfe_price,
                "maePrice": mae_price,
                "stopPrice": stop_price,
                "profitLegs": profit_legs,
                # SCALE-IN lots, absent on any trade that never added — which is every trade of
                # every strategy without the feature. The chart draws one marker per lot, and it
                # has to: `entryPrice`/`exitPrice`/`pnl` alone describe a short exiting BELOW its
                # entry for a P&L of zero, which reads as a bug and is not one.
                #
                # A lot is TRADE-SHAPED — entry, excursion, exit, P&L — so the panel can draw it
                # the way it draws a trade: how far it ran, how far it went against, where it came
                # off. ⚠ Everything past `qty` is OPTIONAL PER LOT and is emitted only when the
                # strategy recorded it. A run whose trades were stored before 2026-08-19 carries
                # `price`/`ms`/`qty` and no more, and nothing backfills it — the panel degrades to
                # the plain `Add` line it drew before, which is the honest picture of a record that
                # never held the rest. **An absent field is never defaulted to 0.0 here**: a lot
                # reported as exiting at price zero is a measurement, and this one was not made.
                **(
                    {
                        "adds": [
                            {
                                "price": round(float(a["price"]), 5),
                                "ms": int(a.get("ms") or 0),
                                "qty": float(a.get("qty") or 0.0),
                                **{
                                    key: round(float(a[src]), 5)
                                    for src, key in (
                                        ("mfe_price", "mfePrice"),
                                        ("mae_price", "maePrice"),
                                        ("exit_price", "exitPrice"),
                                    )
                                    if isinstance(a.get(src), (int, float))
                                },
                                **(
                                    {"exitTime": int(a["exit_ms"])}
                                    if isinstance(a.get("exit_ms"), (int, float))
                                    else {}
                                ),
                                **(
                                    {"exitReason": str(a["exit_reason"])}
                                    if a.get("exit_reason")
                                    else {}
                                ),
                                **(
                                    {"pnl": round(float(a["pnl_usd"]), 2)}
                                    if isinstance(a.get("pnl_usd"), (int, float))
                                    else {}
                                ),
                            }
                            for a in (p.get("adds") or [])
                            if isinstance(a, dict) and isinstance(a.get("price"), (int, float))
                        ]
                    }
                    if p.get("adds")
                    else {}
                ),
                # The trade's exit RUNGS in the strategy's own ladder order, one `{price, banks?}`
                # each — see `_tp_targets`. The chart draws an unhit target faintly so a runner's
                # near-miss is visible, and draws a rung that banks NOTHING under a different name
                # because it is not a target. ⚠ Ladder order is the strategy's, NOT nearest-first:
                # a re-entry prices its first rung off risk and its second off a fib, so the second
                # can be the nearer of the two (23 of the 45 re-entries on run 687c8df2a523; all
                # 160 main entries are correctly ordered). Empty for a trade carrying no rungs.
                "tpTargets": tp_targets,
                # The fib LEG the trade was priced off, plus where the entry and the deepest adverse
                # price sat ON it. OPTIONAL: absent for any runner or strategy that doesn't record one
                # (NT8/MT5, older Python runs, the B-LEG fork), which is what makes the chart's Trade
                # fibs toggle disappear rather than render an empty layer.
                **({"fib": fib} if fib else {}),
            }
        )
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
            for r in (raw_reasons or [])
            if isinstance(r, dict)
        ]
        if not reasons:
            continue  # a record naming no rule can't be filtered or explained — drop it
        out.append(
            {
                "id": f"B{i}",
                "time": int(t),
                "dir": "short" if str(b.get("direction", "")).lower().startswith("s") else "long",
                "price": float(b.get("edge") or 0.0),
                "reasons": reasons,
            }
        )
    return out


def reversal_anchors(
    trades: list[dict],
    misses: list[dict],
) -> list[tuple[int, str, Optional[int], str, Optional[float]]]:
    """Where the Candlestick Reversals layer is allowed to paint a candle.

    **The whole rule, and it is Aaron's (2026-08-08): trades, win or lose, and 3/3 misses. Nothing
    else.** Public and named rather than inline because it is the one thing about this layer that
    has already been got wrong once, and it is not derivable from anything else on the spec.

    ⚠ **BLOCKED setups are deliberately NOT anchors.** They were until this was read on a real
    chart: 324 of them on the reference run against 159 trades and 35 three-of-three misses, so they
    were two thirds of every mark — and the Blocked layer defaults OFF, so they painted navy candles
    in places the reader could see no setup at all. That reads as the layer firing at random, which
    is exactly how it was reported.

    ⚠ **A 2/3 miss is excluded for a different reason** — it was never a setup, so there is no
    "which candle turned it" to ask. `of > 0` guards a record that states no score at all rather
    than letting `0 >= 0` admit it.

    **Each anchor is `(start, direction, end)` and it is a SPAN, not a point** — the layer paints
    every pattern candle from `start` to wherever price ran furthest against the setup inside it.

      - a TRADE spans its ENTRY to its EXIT, win or lose. Aaron: *"you don't only have to give me
        the deepest candle — you could give me all the candles that would have shown a possible
        reversal all the way up to the deepest one … I could see, wow, I could have taken a trade
        at 0.702 or 0.786."* The span is the retracement he entered into, so the marks in it are
        the fib levels that had a reversal candle behind them.
      - a 3/3 MISS spans its RETRACE — the bar price first tagged the zone, to the deepest bar of
        that visit. Aaron: *"I'm expecting it to be that price got into the zone for the trade, and
        there was a reversal candle, but maybe there was a missing confluence point."*

    🔴 **A miss anchors on `zoneTime`/`zoneTurn`, NEVER on `time`, and that distinction is this
    function's reason to exist.** `time` is the bar the setup DIED, which is a median 18 and up to
    718 bars after the retrace it was waiting on and, measured on the reference run, leaves price a
    median $22 and up to $205 from the setup's own entry edge. Anchoring there painted candles in a
    part of the chart the setup had nothing to do with — reported off a real screen as marks
    printing "on the opposite side". ⚠ **`time` is not usable as the span's END either**: over a
    718-bar range the deepest price routinely belongs to a completely different move, which is why
    the strategy records the turn rather than letting this derive it.

    A run made before the strategy recorded those fields yields NO miss anchors at all, and that is
    deliberate — drawing nothing is honest about a question the run cannot answer, and drawing it in
    the old place is not. Rerun the backtest to get them.

    **The fourth element is the OUTCOME, and it decides which candle gets NAMED** — see
    `candle_overlays._wanted_direction`. A winner and a miss want the candle that would have turned
    price the setup's way; a LOSER wants the one that turned it against, because that is the candle
    that explains what happened (Aaron, 2026-08-08: *"if I lost it should default to the candle that
    signaled why I lost"*). It changes no mark's colour and hides nothing — only which of a span's
    marks is its `deepestOf`, and therefore which name the trade's chip carries.

    ⚠ **A miss is `"miss"`, not `"loss"`, even though no trade was taken.** It is a setup that was
    never entered, so the question is *which candle could I have entered on* — the winner's
    question. Filing it as a loss would name it after the candle that killed a trade nobody had.

    **The fifth element is the ENTRY PRICE, and it is what makes a trade's span cover its whole
    DRAWDOWN** rather than stopping two bars past the adverse extreme — see
    `candle_overlays._drawdown_end`, and Aaron's report that candles he could have entered on were
    going unmarked. ⚠ **A MISS passes `None` on purpose: no position was opened, so it has no
    drawdown**, and its span is already the visit into the zone.
    """
    return [
        (
            t["entryTime"],
            t["dir"],
            t["exitTime"],
            "win" if (t.get("pnl") or 0) > 0 else "loss",
            t.get("entryPrice"),
        )
        for t in trades
    ] + [
        (m["zoneTime"], m["dir"], m["zoneTurn"], "miss", None)
        for m in misses
        if m["of"] > 0 and m["met"] >= m["of"] and m.get("zoneTime") and m.get("zoneTurn")
    ]


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
            for r in (m.get("reasons") or [])
            if isinstance(r, dict)
        ]
        if not reasons:
            continue  # a record naming nothing can't be filtered or explained — drop it
        is_near = bool(m.get("near", True))
        for r in reasons:
            if r["label"] not in all_labels:
                all_labels.append(r["label"])
            if is_near:
                near_labels.add(r["label"])
        ms = lambda v: int(v) if isinstance(v, (int, float)) else None
        out.append(
            {
                "id": f"M{i}",
                "time": int(t),
                # The RETRACE — first bar in the zone, and the deepest bar of that visit. The only
                # honest bracket for anything asking what price DID here, because `time` is the bar
                # the setup died. Absent on a run made before the strategy recorded them, and absent
                # means absent.
                "zoneTime": ms(m.get("zone_time_ms")),
                "zoneTurn": ms(m.get("zone_turn_ms")),
                "dir": "short" if str(m.get("direction", "")).lower().startswith("s") else "long",
                "price": float(m.get("edge") or 0.0),
                "met": int(m.get("met") or 0),
                "of": int(m.get("of") or 0),
                "near": is_near,
                "metLines": [str(s) for s in (m.get("met_lines") or [])],
                "reasons": reasons,
            }
        )
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
    atr = sum(trs[:period]) / period  # seed = SMA of first `period` TRs
    out[daily[period]["time"]] = atr  # trs[i] belongs to daily[i+1]
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
        out[daily[i + 1]["time"]] = atr
    return out


def _build_structure(
    m15: list[dict],
    trades: list[dict],
    daily: list[dict],
    params: dict,
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
        overlays.append(
            {
                "type": "box",
                "group": "ORB Range",
                "t0": a0,
                "t1": a1,
                "top": hi,
                "bottom": low,
                "style": {
                    "color": "#2dd4bf",
                    "fillColor": "rgba(45,212,191,0.20)",
                    "lineStyle": "dashed",
                },
            }
        )
        atr = atr_before(day)
        if atr:
            overlays.append(
                {
                    "type": "hline",
                    "group": "ORB Range",
                    "t0": a1,
                    "t1": t_flat,
                    "price": round(hi + buffer_atr * atr, 5),
                    "style": {"color": "#33ff99", "lineStyle": "dashed"},
                }
            )
            overlays.append(
                {
                    "type": "hline",
                    "group": "ORB Range",
                    "t0": a1,
                    "t1": t_flat,
                    "price": round(low - buffer_atr * atr, 5),
                    "style": {"color": "#ff6680", "lineStyle": "dashed"},
                }
            )

    indicators = (
        [
            {
                "name": f"ATR({period}) D1",
                "params": {"period": period},
                "pane": "sub",
                "series": atr_series,
            }
        ]
        if atr_series
        else []
    )
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

    # Liquidity levels — the pools that were live when something fired, and WHICH OF THEM PRICE HAD
    # ALREADY TAKEN. Same anchor rule again, and it is doing more work here than for the gaps: a
    # 6.5-year run creates 35,028 levels (measured) against ~2,800 gaps, because the H4 tier rolls six
    # times a day, so drawing them all would have silently truncated the oldest at the per-group cap.
    # Anchored it is 8,174, of which 4,608 are swept — and the swept ones are the read.
    # Three groups rather than one (Daily/Weekly · Sessions · H4), because the tiers differ by an
    # order of magnitude in volume; see liquidity_overlays.py.
    overlays = overlays + build_liquidity_overlays(candles, anchors)

    # Candlestick reversals — ONE candle repainted per setup, and the only layer here whose anchor
    # set is NARROWER than the `anchors` above: trades and 3/3 misses only, no blocked setups. See
    # `reversal_anchors` for why that is the feature rather than a filter.
    overlays = overlays + build_candle_overlays(candles, reversal_anchors(trades, misses))

    # Session VWAP — a main-pane line off the canonical engine, default OFF. It is the one layer
    # here that needs the bar's VOLUME, so it returns None (no toggle) whenever the run's bars
    # carry none; see vwap_overlays.py for why a missing volume is a refusal rather than a zero.
    vwap = build_vwap_indicator(candles)
    if vwap:
        indicators = indicators + [vwap]

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
    log.info(
        "chart_spec: built for %s — %d candles, %d trades, %d overlays, %d indicators (%s)",
        run_id,
        len(candles),
        len(trades),
        len(overlays),
        len(indicators),
        base_tf,
    )
    return spec


#: The overlay groups every leg computes for ITSELF, anchored to that leg's own trades / blocked /
#: missed bars. They are the ones a merged stack has to carry PER LEG rather than once — see
#: `build_stack_chart_spec`.
_ANCHORED_GROUPS = (GROUP_FVG, GROUP_OB, *GROUPS_LIQ)


def _overlay_identity(o: dict) -> tuple:
    """What makes two legs' copies of one anchored overlay the SAME drawing.

    A fair value gap, an order block and a liquidity level are facts about the MARKET; two legs that
    both fired near one gap each report it, and drawing it twice would double the layer's box count
    and stack two identical rectangles. Geometry plus the label IS the identity — nothing here is
    per-leg — so the dedupe merges their `layers` instead.
    """
    return (
        o.get("group"),
        o.get("type"),
        o.get("t0"),
        o.get("t1"),
        o.get("t"),
        o.get("p0"),
        o.get("p1"),
        o.get("price"),
        o.get("label"),
    )


def build_stack_chart_spec(stack_id: str, refresh: bool = False) -> Optional[dict]:
    """Build a MERGED ChartSpec for a portfolio stack — one shared candle chart carrying every
    completed leg's trades, blocked setups, missed setups and anchored analysis, each tagged with
    `layer` = its strategy_id so the frontend can filter by the SAME per-strategy toggle it uses for
    the equity chart (and colour each layer to match).

    Reuses each leg's own `build_chart_spec` (all legs share one instrument/TF/window, so the
    candles are identical). Returns None if the stack is unknown; a spec with empty candles if no
    leg produced any (frontend shows "no price data"). Not cached (legs can complete
    incrementally); each leg's own spec is cached, so the merge is cheap.

    ⚠ **`refresh=True` rebuilds EVERY leg's own spec, and that is where the cost is.** The merge
    itself holds no cache to drop — it is recomputed on every request — so a Rebuild that only
    re-ran the merge would hand back the identical stale layers and read as a broken button. It is
    therefore N leg rebuilds, each re-fetching candles and replaying the engines, which is what a
    Rebuild on each leg's own page would cost anyway. Every leg is rebuilt rather than the base one
    alone: blocked setups, missed setups and the anchored analysis come from EACH leg's spec, so
    refreshing only the leg that supplies the candles would leave most of the chart stale.

    🔴 **Blocked setups, missed setups and the anchored analysis groups were DROPPED here until
    2026-08-10, and the reason given was that none of them carried a `layer`.** That was true and
    it was an argument for TAGGING them, not for omitting them: with the layers off, isolating one
    strategy on a stack left the reader with winners, losers and fibs while a single backtest of the
    same strategy had ten more rows. Reported off the screen in exactly those words — *"I don't have
    all my analysis tools… fair value gaps are gone, missed trades, blocked trades, all that stuff
    is gone."*

    Two rules hold the merge together, and they differ because the layers answer different
    questions:

      - **A block or a miss belongs to ONE strategy.** It is that strategy's own rule refusing its
        own setup, so it is tagged and never deduped — two legs refusing on the same bar are two
        separate facts, and merging them would erase whose rule spoke.
      - **A gap, an order block and a liquidity level are facts about the MARKET**, selected for
        drawing by whichever leg fired near them. So identical copies from two legs are ONE overlay
        carrying both layers (`_overlay_identity`), and it draws while EITHER leg is shown. Keeping
        two would double the box count the menu reports and stack two identical rectangles.

    ⚠ **The structure overlays and the indicators still come from the BASE leg alone**, unchanged:
    they are computed from the candles rather than from any leg's trades, so every leg's copy is
    byte-identical and a merge would be N copies of one answer.

    ⚠ **CANDLESTICK REVERSALS ARE STILL DROPPED, and this is the one genuine refusal left.** A
    candle mark carries `spans` / `deepestOf` / `deepestNames` as INDICES into its own run's anchor
    list (`reversal_anchors`: that run's trades, then its 3/3 misses). A stack re-sorts every leg's
    trades into one list by entry time AND `StackDetail` filters that list by which legs are switched
    on — so an index minted against one run addresses a different trade here, and would name the
    wrong trade's outcome chip. That is a defect that renders a confident wrong answer rather than a
    missing layer, which is the worse of the two. Carrying it needs the marks to reference a trade's
    ID rather than its position; a leg's own page has the layer in the meantime.
    """
    rows = lab_db.list_stack_runs(stack_id)
    if not rows:
        return None

    first_spec: Optional[dict] = None
    base_spec: Optional[dict] = None  # first leg that actually has candles
    base_run_id: Optional[str] = None  # its run_id — drives the price chart's drill-down/fullscreen
    all_trades: list[dict] = []
    all_blocks: list[dict] = []
    all_misses: list[dict] = []
    miss_noise: list[str] = []
    layers: list[dict] = []
    # Anchored overlays, keyed by identity so two legs reporting one market fact land on one entry.
    anchored: dict[tuple, dict] = {}

    for r in rows:
        if r["status"] != "complete":
            continue
        spec = build_chart_spec(r["run_id"], refresh)
        if not spec:
            continue
        sid = r["strategy_id"]
        first_spec = first_spec or spec
        if base_spec is None and spec.get("candles"):
            base_spec = spec
            base_run_id = r["run_id"]
        layers.append(
            {
                "strategy_id": sid,
                "strategy_name": r.get("strategy_name", ""),
                "run_id": r["run_id"],
            }
        )
        for tr in spec.get("trades", []):
            t = dict(tr)
            t["layer"] = sid
            t["id"] = f"{sid}:{tr.get('id', '')}"  # unique across layers
            all_trades.append(t)
        for b in spec.get("blocks", []):
            bl = dict(b)
            bl["layer"] = sid
            bl["id"] = f"{sid}:{b.get('id', '')}"
            all_blocks.append(bl)
        for m in spec.get("misses", []):
            ms = dict(m)
            ms["layer"] = sid
            ms["id"] = f"{sid}:{m.get('id', '')}"
            all_misses.append(ms)
        # A union, order-preserving. `missNoise` is a list of reason LABELS to open unticked, and a
        # label one leg calls routine is routine on the merged chart too — a leg that never produced
        # it has no opinion, so it cannot vote against.
        for lbl in spec.get("missNoise", []):
            if lbl not in miss_noise:
                miss_noise.append(lbl)
        for o in spec.get("overlays", []):
            if o.get("group") not in _ANCHORED_GROUPS:
                continue
            key = _overlay_identity(o)
            hit = anchored.get(key)
            if hit is None:
                ov = dict(o)
                ov["layers"] = [sid]
                anchored[key] = ov
            elif sid not in hit["layers"]:
                hit["layers"].append(sid)

    src = base_spec or first_spec
    if src is None:
        return None

    all_trades.sort(key=lambda t: t.get("entryTime", 0))
    # Structure overlays + indicators are a property of the MARKET on these candles, not of any one
    # strategy — identical for every leg (same instrument/timeframe/window). So the stack's price
    # chart carries the base leg's, giving it full BacktestDetail parity (structure layers, ATR pane,
    # fib/measurement tools all read the same spec). The anchored groups are merged above instead,
    # and the candle marks are dropped — see the docstring for why that one cannot be merged.
    overlays = [
        dict(o)
        for o in src.get("overlays", [])
        if o.get("group") not in (*_ANCHORED_GROUPS, GROUP_CANDLES)
    ]
    overlays.extend(anchored.values())

    return {
        "instrument": src["instrument"],
        "baseTimeframe": src["baseTimeframe"],
        "runTimeframe": src.get("runTimeframe", src["baseTimeframe"]),
        "historyStartMs": src.get("historyStartMs"),
        "brokerGmtOffsetHours": src["brokerGmtOffsetHours"],
        "candles": src["candles"],
        "sessions": [dict(s) for s in src.get("sessions", [])],
        "trades": all_trades,
        "blocks": all_blocks,
        "misses": all_misses,
        "missNoise": miss_noise,
        "overlays": overlays,
        "indicators": [dict(i) for i in src.get("indicators", [])],
        "layers": layers,
        # The base leg's run_id — the frontend routes M1/M5 drill-down + fullscreen candle fetches
        # through it (all legs share the same feed, so any leg's candles are the stack's candles).
        "base_run_id": base_run_id or (rows[0]["run_id"] if rows else None),
    }


# How close the oldest bar returned must sit to the broker's measured floor before we will call it
# the broker's own limit. The floor is a DATE and the bar is a timestamp, and history starts
# mid-session on the first day (Vantage XAUUSD M15 opens 2018-09-13 with 38 bars), so the comparison
# needs a day or so of slack in each direction — but nothing like enough to cover a cache hole,
# which is what this exists to refuse.
_FLOOR_SLOP_MS = 3 * 86_400_000


def _is_broker_floor(instrument: str, timeframe: str, data_start_ms: int, runner: str) -> bool:
    """Is this oldest-bar timestamp the broker's REAL start of history for this timeframe?

    Answers False whenever it cannot be sure — an unmeasurable floor, a runner with no floor
    concept, or an unreachable terminal. See the `hard_edge` note in `build_run_candles`: the
    caller turns True into a red "nothing older exists" line AND into a signal to stop paging,
    so a wrong True is unrecoverable while a wrong False costs one request.
    """
    try:
        limit = history_limits.limits_for(
            instrument, "Minute", _TF_MIN.get(timeframe.upper(), 15), runner
        )
    except Exception:
        return False
    earliest = (limit or {}).get("earliest_date")
    if not earliest:
        return False
    floor_ms = int(datetime.fromisoformat(earliest).replace(tzinfo=timezone.utc).timestamp() * 1000)
    return data_start_ms - floor_ms <= _FLOOR_SLOP_MS


def _drill_structure(candles: list[dict], from_ms: int, to_ms: int) -> list[dict]:
    """Market structure for a DRILL-DOWN window, computed on the bars the reader is looking at.

    🔴 **Structure used to be computed ONCE, on the run's own timeframe, and drawn over whatever
    candles were on screen — so a drill-down painted the base timeframe's swings on top of finer
    bars.** Reported by Aaron on 2026-08-08 against the M5 drill-down of a 15m run: the chart's own
    OHLC readout was the M5 bar (`C 4,339.80  V 908`) while every label on it came from the M15
    replay — `SOS @4242.99`, `iSL @4247.23` — prices that are not swings on the bars underneath.
    The M5 answer is `SOS @4224.73`, which is what TradingView drew for the same window. **Nothing
    errored, both halves were internally correct, and the chart read as an engine that disagreed
    with the indicator it was ported from.**

    ⚠ **`candles` must already carry `_DRILL_WARMUP_BARS` of context in front of `from_ms`** — see
    that constant. Only overlays whose span reaches into `[from_ms, to_ms]` are returned, so the
    warm-up is context and never content.

    ⚠ **Internal content is demoted to HISTORIC.** `build_market_structure_overlays` calls the
    newest leg in whatever it replayed "current", and a drill-down window ends at the reader's
    viewport rather than at the run — so paging older would mint a second, third, fourth "current"
    leg, for a group whose entire meaning is *the leg this run is in now*. Same call the deleted
    `_demote_page_internal` made, for the same reason.
    """
    if not candles:
        return []
    try:
        overlays = build_market_structure_overlays(candles)
    except Exception as exc:  # noqa: BLE001 — a page is about its BARS; structure is a bonus
        log.warning("drill structure: replay failed: %s", exc)
        return []

    out: list[dict] = []
    for ov in overlays:
        start = ov["t"] if ov["type"] == "label" else ov["t0"]
        end = ov["t"] if ov["type"] == "label" else ov["t1"]
        if end < from_ms or start > to_ms:
            continue
        if ov["group"] == GROUP_INTERNAL:
            ov["group"] = GROUP_INTERNAL_HISTORIC
            ov["requires"] = [GROUP_INTERNAL]
        elif ov.get("requires") == [GROUP_INTERNAL]:
            ov["requires"] = [GROUP_INTERNAL, GROUP_INTERNAL_HISTORIC]
        out.append(ov)
    return out


def build_run_candles(
    run_id: str,
    timeframe: str,
    from_ms: int,
    to_ms: int,
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
      - {instrument, timeframe, candles, available, feed_error, data_start_ms, hard_edge}.
        `available` is False ONLY when the feed could not be ASKED (the MT5 agent or its terminal
        is down), with `feed_error` naming the failure; an empty `candles` list under
        `available: true` is the feed answering that it has nothing for that window. `hard_edge` is True when the oldest bar returned is the
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
    # ⚠ The START is widened FURTHER, by `_DRILL_WARMUP_BARS` of this timeframe, so the structure
    # engine has context to replay through before the window the reader sees. Calendar days rather
    # than trading days (`* 7 / 5`), because the fetch is stated in dates and a weekend carries no
    # bars. Those extra bars are trimmed out of `candles` below — they are NEVER shipped, so
    # `data_start_ms` and `hard_edge` still describe the window that was asked for.
    warmup_ms = int(_DRILL_WARMUP_BARS * tf_min * 60_000 * 7 / 5)
    fetch_from_ms = from_ms - warmup_ms
    start_date = datetime.fromtimestamp(fetch_from_ms / 1000, tz=timezone.utc).date().isoformat()
    end_date = datetime.fromtimestamp(to_ms / 1000, tz=timezone.utc).date().isoformat()
    fetched, feed_error = _fetch_candles(instrument, start_date, end_date, timeframe, runner)
    if feed_error is not None:
        # ⚠ The warm-up must never be able to REFUSE a window the reader could otherwise see.
        # Reaching back 2,000 bars can cross the broker's measured history floor, and `BarSource`
        # raises on that — so a drill-down near the start of history would come back
        # `available: false` for bars the feed holds. Context is a bonus; the window is the point.
        log.info("run_candles: warmed fetch failed (%s) — retrying bare window", feed_error)
        bare_start = datetime.fromtimestamp(from_ms / 1000, tz=timezone.utc).date().isoformat()
        fetched, feed_error = _fetch_candles(instrument, bare_start, end_date, timeframe, runner)
    fetched = [c for c in fetched if c["time"] <= to_ms]
    # Structure is read off the WARMED series; the window itself is what gets shipped.
    overlays = _drill_structure(fetched, from_ms, to_ms)
    candles = [c for c in fetched if from_ms <= c["time"]]
    data_start_ms = candles[0]["time"] if candles else None
    # True broker limit ⇔ data exists, its oldest bar is well past what we asked for (beyond a
    # weekend/holiday gap), OUR cap didn't clip the request, AND that oldest bar is sitting on the
    # broker's MEASURED history floor.
    #
    # 🔴 **That last clause was missing until 2026-08-07, and without it this inferred a fact about
    # the BROKER from a fact about OUR CACHE.** Aaron drilled to M1 and got ~100 bars flagged
    # "No earlier M1 data — all the broker still has", on a symbol whose real M1 history runs back
    # to 2018-09-14. The cache had a 45-day hole its `ranges.json` claimed to cover
    # (`backtest/data/source.py::covered_spans`), so the fetch honestly returned nothing older —
    # and this turned "we have no more" into "there IS no more". The frontend then STOPS PAGING on
    # a hard edge, so the claim was self-sealing: nothing would ever ask for the missing bars again.
    #
    # ⚠ **An unknown floor answers False, never True.** No measurement means no claim — the pager
    # pays one extra round trip at the real edge and gets an empty answer, which is the honest way
    # to find a boundary. That is also why NT8/MT5 never report a hard edge here: `limits_for` is
    # python-only by design (those runners read history from their own terminals), so there is no
    # measured floor to check against and a confident red line would be pure invention.
    #
    # ⚠ **The flag is now RARELY true in practice, and that is the fix working rather than the flag
    # dying.** MEASURED against the live backend after the cache repair: a python drill-down that
    # reaches the real floor is refused by `BarSource.load`'s own floor guard BEFORE any fetch, so
    # it returns `available: false` carrying the measured sentence ("XAUUSD has no real 1-minute
    # history before 2018-09-14 on VantageMarkets-Demo"), which the chart prints — strictly better
    # than a red line with no explanation. The pager stops either way, since a page with no bars
    # answers `more: false`. Do not delete the flag because it seldom fires.
    hard_edge = (
        bool(candles)
        and not clamped
        and (data_start_ms - from_ms) > _HARD_EDGE_SLOP_MS
        and _is_broker_floor(instrument, timeframe, data_start_ms, runner)
    )
    out = {
        "instrument": instrument,
        "timeframe": timeframe.upper(),
        "candles": candles,
        # ⚠ **`available` is whether the feed could be ASKED, not whether it had anything.** It was
        # `bool(candles)` until 2026-08-07 — the same fact as `candles == []`, so a caller could not
        # tell a dead MT5 agent from a broker with no 1m history back that far, and the chart's
        # drill-down hedged in a message rather than saying which. `available: true` with an empty
        # list is now a real answer: the feed replied and has nothing for this window.
        "available": feed_error is None,
        "feed_error": feed_error,
        "data_start_ms": data_start_ms,
        "hard_edge": hard_edge,
        # Structure computed ON THESE BARS. The panel swaps it in for the spec's base-timeframe
        # overlays while a drill-down is showing — see `_drill_structure`.
        "overlays": overlays,
    }
    log.info(
        "run_candles: %s %s [%s, %s] -> %d candles, %d overlays (hard_edge=%s, feed_error=%s)",
        run_id,
        timeframe,
        start_date,
        end_date,
        len(candles),
        len(overlays),
        hard_edge,
        feed_error,
    )
    return out
