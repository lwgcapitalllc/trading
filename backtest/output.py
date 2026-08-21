"""A3 — the output adapter: a finished trade list → the shape the lab consumes.

`build_results(trades, ...)` returns `{equity_curve, daily_pnl, kpis, engine_trades}` —
the same four keys `runner_dispatch._normalize_mt5_results` hands back for an MT5 run, so
every downstream consumer (evaluator, worthiness, stress tests, the BacktestDetail charts)
reads a Python run without knowing it is one.

Strategy-agnostic by design: the input is a sequence of any object carrying the
`backtest`-wide trade attributes (dir, entry/exit index+ms+price, qty, pnl_usd,
stop_distance, exit_reason) — `strategies.python.mpc_sos_fade.execution.Trade` satisfies it,
and so must any future Python strategy. This module owns NO strategy logic and no fill
logic; it is pure reporting arithmetic over trades someone else already produced.

Two contracts are deliberately mirrored rather than imported (this package must stay
importable without the FastAPI app, per backtest/CLAUDE.md):
  * the equity-curve point — `backtest_runner.parse_trades_csv`
  * `engine_trades` rows   — `sizing_engine.RawTrade` (the runner→engine contract)
Both are locked by `tests/test_output.py`; if the lab's shape moves, that test fails.

**Units:** `win_rate` is a FRACTION (0.0-1.0), matching `sizing_pipeline` and the lab's
regime rows — the frontend's `pct()` multiplies by 100 to display it. It shipped as a
percent once and rendered as "7273.0%".

**Not computed here:** `sharpe` / `platform_sharpe` / `sharpe_low_sample`. The lab owns the
canonical Sharpe (`metrics.apply_canonical_sharpe`) and applies it at run completion from
`daily_pnl`; computing a second one here would be the duplicate-definition bug that doc
warns about. Same for regime tags (the lab tags `daily_pnl` itself) and `cagr`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Sequence

__all__ = [
    "build_results",
    "build_equity_curve",
    "build_daily_pnl",
    "build_kpis",
    "build_engine_trades",
    "engine_trades_csv",
    "build_blocked_setups",
    "build_missed_setups",
]


def _utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _date(ms: int) -> str:
    return _utc(ms).strftime("%Y-%m-%d")


def _round(x: float, n: int = 2) -> float:
    return round(float(x), n)


def _stop_price(t: Any) -> float:
    """Initial 1R stop as a PRICE, from `stop_distance` + direction + entry. `stop_distance` is
    entry→the stop frozen at placement (always ≥ 0), so a long's stop sits below entry and a
    short's above: `entry - dir*stop_distance`. Returns 0.0 for a trade duck-type lacking either."""
    entry = getattr(t, "entry_price", 0.0)
    dist = getattr(t, "stop_distance", 0.0)
    if not entry or not dist:
        return 0.0
    return entry - (1.0 if t.dir > 0 else -1.0) * dist


# ── equity curve ──────────────────────────────────────────────────────────────


def build_equity_curve(trades: Sequence[Any], *, initial_capital: float = 0.0) -> list[dict]:
    """One point per CLOSED trade, in exit order — the lab's equity-curve contract.

    `equity` is cumulative net P&L anchored on `initial_capital` (the NT8 path anchors on
    0.0 because its CSV reports cumulative profit, not balance; both are accepted since
    every consumer rebases the curve against a ruleset's account_size anyway).

    `direction` is the NT8 vocabulary ("Long"/"Short") because `metrics.compute_regime_breakdown`
    and the Long-vs-Short breakdown match on those exact strings. `long + short == trade_count`
    holds here by construction — one point per trade, never keyed by timestamp (the MT5 path's
    minute-resolution collapse bug is impossible in this shape).
    """
    curve: list[dict] = []
    equity = float(initial_capital)
    for i, t in enumerate(sorted(trades, key=lambda x: (x.exit_ms, x.entry_ms)), start=1):
        equity += t.pnl_usd
        fib = _trade_fib(t)
        curve.append(
            {
                "index": i,
                "equity": _round(equity),
                "date": _date(t.exit_ms),
                "entry_ms": int(t.entry_ms),
                "direction": "Long" if t.dir > 0 else "Short",
                "profit": _round(t.pnl_usd),
                "exit_name": t.exit_reason or None,
                "size": t.qty,
                "favorable": _round(getattr(t, "mfe_usd", 0.0)),
                "adverse": _round(getattr(t, "mae_usd", 0.0)),
                # Commission + swap + slippage charged to THIS trade, negative. `profit` is already
                # net of it — this carries what the costs actually WERE, which is otherwise
                # uninspectable: a run can now be priced (2026-08-01) and a reader had no way to see
                # how much of a shortfall was friction. 0.0 on a run that stated no costs, which is an
                # honest "nothing was priced" rather than a claim that trading was free.
                "costs_usd": _round(getattr(t, "costs_usd", 0.0)),
                # The trade's R, COPIED from the strategy rather than re-derived downstream. `profit`
                # is rounded to cents and `stop_price` to 5dp, so a consumer recovering R as
                # profit / (entry-stop) / size lands ~4e-6 out per trade — invisible on one row, and it
                # compounds to ~0.06% of final equity once `backtest/reprice.py` re-walks a curve with
                # it. Carrying the number the strategy already had removes the derivation entirely.
                # Reporting-only, and optional: a trade duck-type without `r` simply omits it.
                **(
                    {"r": _round(t.r, 6)} if isinstance(getattr(t, "r", None), (int, float)) else {}
                ),
                # The DOLLARS this trade put at risk — its own 1R. With `r` above it describes the
                # trade completely and exactly (`profit == r * risk_usd`), which is what lets a
                # re-price re-walk the balance without recovering the risk from a 5dp stop price and a
                # size. Also the honest source for "what fraction of the account did this risk?": it is
                # NOT the configured risk %, because a resting limit is SIZED WHEN PLACED and the
                # balance moves before it fills. Reporting-only, optional.
                **(
                    {"risk_usd": _round(t.stop_distance * t.qty, 4)}
                    if getattr(t, "stop_distance", 0.0) and t.qty
                    else {}
                ),
                # Real fills + which layer traded — the price chart draws the trade box at the exact
                # entry/exit price (not a candle-close guess) and tells primary from secondary. Optional
                # for consumers that don't read them; every other equity-curve reader ignores extra keys.
                "exit_ms": int(t.exit_ms),
                "entry_price": _round(getattr(t, "entry_price", 0.0), 5),
                "exit_price": _round(getattr(t, "exit_price", 0.0), 5),
                "kind": getattr(t, "kind", "primary"),
                # Profit-depth trade view (price chart): how far price ran (mfe/mae PRICES), where each
                # rung actually banked (`legs`), and the initial 1R stop. All optional — a runner/trade
                # that doesn't carry them degrades to the plain entry→exit box. Reporting-only.
                "mfe_price": _round(getattr(t, "mfe_price", 0.0), 5),
                "mae_price": _round(getattr(t, "mae_price", 0.0), 5),
                "stop_price": _round(_stop_price(t), 5),
                "legs": [
                    {
                        "reason": lg.get("reason", ""),
                        "price": _round(lg.get("price", 0.0), 5),
                        "ms": int(lg.get("ms", 0)),
                        "qty": lg.get("qty", 0.0),
                    }
                    for lg in getattr(t, "legs", []) or []
                ],
                # SCALE-IN lots this trade actually bought AFTER the entry. Reporting-only and
                # OPTIONAL — a strategy or runner with no scale-in carries none, and the key is then
                # absent rather than an empty list claiming a feature ran.
                # 🔴 It is what makes the row's P&L reconcilable: `size` is the BASE quantity, so a
                # trade that added holds more than `size` says, and `profit` reflects lots this row
                # would otherwise not mention at all. Run 295a6ff29d21 booked 8 trades at exactly
                # $0.00 with an entry above the exit on a short and nothing in the record to say why.
                #
                # Each lot is TRADE-SHAPED — its own entry, its own excursion, its own exit and its
                # own P&L — because a lot IS a position and a reader asks it the same questions. See
                # `mpc_sos_fade.execution.Trade.adds`.
                # ⚠ Everything past `qty` is PER-LOT OPTIONAL and copied only when the strategy
                # recorded it. A run stored before 2026-08-19, and any strategy that adds without
                # tracking its lots, carries the three original keys — and a lot that nothing closed
                # carries no `exit_price` at all. **A default of 0.0 here would report a lot as
                # having exited at price zero**, which is the same "cannot ask reads as measured"
                # shape the bar-cache and the terminal-liveness probe both broke on.
                **(
                    {
                        "adds": [
                            {
                                "price": _round(a.get("price", 0.0), 5),
                                "ms": int(a.get("ms", 0)),
                                "qty": a.get("qty", 0.0),
                                **{
                                    k: (
                                        int(a[k])
                                        if k == "exit_ms"
                                        else a[k]
                                        if k == "exit_reason"
                                        else _round(a[k], 2 if k == "pnl_usd" else 5)
                                    )
                                    for k in (
                                        "mfe_price",
                                        "mae_price",
                                        "exit_price",
                                        "exit_ms",
                                        "exit_reason",
                                        "pnl_usd",
                                    )
                                    if a.get(k) is not None
                                },
                            }
                            for a in getattr(t, "adds", []) or []
                        ]
                    }
                    if getattr(t, "adds", None)
                    else {}
                ),
                # The trade's exit RUNGS, in the strategy's own ladder order — see `_tp_targets`.
                # Empty for a trade duck-type that carries none. Reporting-only.
                "tp_targets": _tp_targets(t),
                # The fib LEG this trade was priced off, exactly as the strategy read it when it
                # placed the order — `{start_ms, levels: [[ratio, price], ...]}`, or absent. See
                # `_trade_fib`. Reporting-only, and optional like every other rich field here.
                **({"fib": fib} if fib else {}),
            }
        )
    return curve


def _tp_targets(t: Any) -> list:
    """A trade's exit RUNGS → the equity point's `tp_targets`, in the strategy's ladder order.

    Two shapes, and which one you get is a statement about what the strategy was able to tell us:

      {"price": p, "banks": bool}   the strategy reported how much each rung takes off, so a
                                    consumer knows whether `p` is a profit target the trade
                                    placed an order at, or a level that banks nothing and only
                                    steps the stop.
      p                             a bare price. The strategy reports rung PRICES and nothing
                                    about orders, so nobody downstream knows which it is.

    🔴 The two must stay distinguishable, and `banks: false` may never stand in for "not
    reported". A chart that renders an unknown rung the same as a known-dead one is claiming a
    measurement nobody made — the same shape as a dead terminal reading as a quiet market. The
    price chart drew both prices as `TP1`/`TP2` until 2026-08-21, which put a green `TP2` chip on
    every trade of a run whose second rung placed no order at all, on any trade.

    Duck-typed like everything else here: `tp_rungs` is the rich form (`(price, banks_pct)` pairs)
    and the `tp1`/`tp2` pair is the fallback, so a strategy that carries neither ships `[]` rather
    than an invented ladder. A rung priced at 0 is unset and is dropped either way.
    """
    rungs = getattr(t, "tp_rungs", None)
    if rungs:
        out = []
        for rung in rungs:
            try:
                price, pct = rung
            except (TypeError, ValueError):
                continue
            if not isinstance(price, (int, float)) or not price:
                continue
            if not isinstance(pct, (int, float)):
                continue
            out.append({"price": _round(price, 5), "banks": pct > 0})
        return out
    return [
        _round(v, 5)
        for v in (getattr(t, "tp1", 0.0), getattr(t, "tp2", 0.0))
        if isinstance(v, (int, float)) and v
    ]


def _trade_fib(t: Any) -> Optional[dict]:
    """A trade's frozen fib leg → the equity point's `fib` object, or None.

    Duck-typed like everything else here: any object exposing `levels` as (ratio, price) pairs
    satisfies it, so this knows nothing about which strategy produced the ladder or which ratios
    are in it — a strategy drawing a different set just ships different pairs.

    It COPIES rather than derives. The prices are the ones the strategy had in hand at placement;
    recomputing them downstream from anchors would be a second implementation of the same fib, and
    the two would eventually disagree about a trade neither could re-run.
    """
    fib = getattr(t, "fib", None)
    raw = getattr(fib, "levels", None) if fib is not None else None
    if not raw:
        return None
    levels = [
        [float(r), _round(p, 5)]
        for r, p in raw
        if isinstance(r, (int, float)) and isinstance(p, (int, float))
    ]
    if not levels:
        return None
    start = getattr(fib, "start_ms", None)
    out: dict = {"levels": levels}
    if isinstance(start, (int, float)) and start:
        out["start_ms"] = int(start)
    return out


# ── daily P&L ─────────────────────────────────────────────────────────────────


def build_daily_pnl(trades: Sequence[Any]) -> list[dict]:
    """Net P&L per calendar UTC day, booked on the EXIT day (the lab's convention —
    `parse_trades_csv` keys `daily_map` off exit time). Days with no closed trade are
    absent, not zero-filled: the trailing-drawdown engine walks the days that exist.
    """
    daily: dict[str, float] = {}
    for t in trades:
        d = _date(t.exit_ms)
        daily[d] = daily.get(d, 0.0) + t.pnl_usd
    return [{"date": d, "pnl": _round(v)} for d, v in sorted(daily.items())]


# ── KPIs ──────────────────────────────────────────────────────────────────────


def _max_drawdown(curve: Sequence[dict], initial_capital: float) -> float:
    """Largest peak-to-trough drop in the closed-trade equity curve, as a POSITIVE
    dollar number (the sign every consumer expects). This is whole-test max DD — the
    lab's PASS/FAIL drawdown is the separate EOD trailing max-loss engine, which
    recomputes from daily_pnl; this KPI is for display and worthiness only.
    """
    peak = float(initial_capital)
    worst = 0.0
    for p in curve:
        eq = p["equity"]
        peak = max(peak, eq)
        worst = max(worst, peak - eq)
    return _round(worst)


def _worst_losing_streak(trades: Sequence[Any]) -> int:
    worst = run = 0
    for t in sorted(trades, key=lambda x: x.exit_ms):
        run = run + 1 if t.pnl_usd < 0 else 0
        worst = max(worst, run)
    return worst


def build_kpis(
    trades: Sequence[Any],
    *,
    initial_capital: float = 0.0,
    equity_curve: Optional[Sequence[dict]] = None,
    daily_pnl: Optional[Sequence[dict]] = None,
) -> dict:
    """The KPI dict the lab reads. Keys mirror what the NT8/MT5 paths supply, so
    worthiness/grading/BacktestDetail need no Python-specific branch.

    Sharpe/sortino/cagr are deliberately ABSENT — see the module docstring (the lab
    stamps canonical Sharpe from daily_pnl at completion).
    """
    curve = list(
        equity_curve
        if equity_curve is not None
        else build_equity_curve(trades, initial_capital=initial_capital)
    )
    days = list(daily_pnl if daily_pnl is not None else build_daily_pnl(trades))

    wins = [t.pnl_usd for t in trades if t.pnl_usd > 0]
    losses = [t.pnl_usd for t in trades if t.pnl_usd < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    n = len(trades)

    # PF is undefined with no losses; report it as 0.0 rather than inf so JSON/compare
    # paths stay total-ordered. Worthiness reads PF < 0.8 as DISCARD, so a lossless
    # strategy would be mis-tiered — but that only occurs with a trade count far below
    # every gate anyway (>=30), and inf breaks the JSON encode outright.
    pf = _round(gross_profit / gross_loss, 3) if gross_loss > 0 else 0.0

    durations = [(t.exit_ms - t.entry_ms) / 60000.0 for t in trades]

    return {
        "net_pnl": _round(sum(t.pnl_usd for t in trades)),
        "gross_profit": _round(gross_profit),
        "gross_loss": _round(gross_loss),
        "profit_factor": pf,
        "trade_count": n,
        "win_count": len(wins),
        "loss_count": len(losses),
        # FRACTION (0.0-1.0), not a percent — the lab-wide convention (sizing_pipeline,
        # metrics regime rows) that every consumer and the frontend's pct() assume.
        "win_rate": _round(len(wins) / n, 4) if n else 0.0,
        "avg_win": _round(gross_profit / len(wins)) if wins else 0.0,
        "avg_loss": _round(-gross_loss / len(losses)) if losses else 0.0,
        "max_drawdown": _max_drawdown(curve, initial_capital),
        "worst_day_pnl": _round(min((d["pnl"] for d in days), default=0.0)),
        "worst_losing_streak": _worst_losing_streak(trades),
        "avg_trade_duration_min": _round(sum(durations) / n, 1) if n else 0.0,
        "total_r": _round(sum(getattr(t, "r", 0.0) for t in trades), 2),
    }


# ── engine_trades (the runner→sizing-engine contract) ─────────────────────────

_ENGINE_TRADE_COLS = (
    "index",
    "entry_time",
    "exit_time",
    "direction",
    "entry_price",
    "exit_price",
    "stop_distance",
    "point_value",
    "commission_per_side",
    "exit_reason",
)


def build_engine_trades(
    trades: Sequence[Any], *, point_value: float, commission_per_side: float = 0.0
) -> list[dict]:
    """Unit-size trade records for `sizing_engine.RawTrade` — the contract that lets a
    Python run flow through the dynamic sizing engine exactly like ORB/LondonBreakout.

    `stop_distance` is why this must come from the STRATEGY and cannot be re-derived from
    a trade export (see RawTrade's docstring): only the strategy knows the 1R it sized
    against. Times are ISO-8601 UTC.
    """
    out: list[dict] = []
    for i, t in enumerate(sorted(trades, key=lambda x: (x.exit_ms, x.entry_ms)), start=1):
        out.append(
            {
                "index": i,
                "entry_time": _utc(t.entry_ms).isoformat(),
                "exit_time": _utc(t.exit_ms).isoformat(),
                "direction": 1 if t.dir > 0 else -1,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "stop_distance": t.stop_distance,
                "point_value": point_value,
                "commission_per_side": commission_per_side,
                "exit_reason": t.exit_reason or "",
            }
        )
    return out


def engine_trades_csv(rows: Iterable[dict]) -> str:
    """`engine_trades.csv` text — the same file ORB.cs and LondonBreakout.mq5 write, so
    the lab's existing reader path needs no Python-specific branch."""
    import csv
    import io

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(_ENGINE_TRADE_COLS), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r[k] for k in _ENGINE_TRADE_COLS})
    return buf.getvalue()


# ── the one entry point ───────────────────────────────────────────────────────


def build_blocked_setups(blocks: Optional[Sequence[Any]]) -> list[dict]:
    """A strategy's refused setups → the lab's blocked-setup contract (the price chart's
    "why didn't this trade" markers).

    A blocked setup places no order, so it appears in no trade list and no equity curve —
    this is the only channel it reaches the lab through. Strategy-agnostic like everything
    else here: the input is any object carrying `dir` / `time_ms` / `edge` plus parallel
    `labels` and `reasons` sequences (`mpc_sos_fade.execution.BlockedSetup` satisfies it),
    and a strategy that records none simply produces `[]`.

    A setup can be refused by SEVERAL rules at once, so `reasons` is a LIST — that is what
    lets the chart filter by reason without lying ("blocked by the veto" has to stay true
    when something else was also blocking). The list is ordered by the strategy's own
    precedence, so `reasons[0]` is the primary one.
    """
    out: list[dict] = []
    for b in blocks or []:
        labels = list(getattr(b, "labels", None) or [])
        texts = list(getattr(b, "reasons", None) or [])
        reasons = [
            {"label": str(labels[i]), "reason": str(texts[i] if i < len(texts) else "")}
            for i in range(len(labels))
        ]
        out.append(
            {
                "time_ms": int(getattr(b, "time_ms", 0)),
                "direction": "Long" if getattr(b, "dir", 0) > 0 else "Short",
                "codes": [int(c) for c in (getattr(b, "codes", None) or [])],
                "reasons": reasons,
                "edge": _round(float(getattr(b, "edge", 0.0)), 5),
            }
        )
    out.sort(key=lambda r: r["time_ms"])
    return out


# How many confluences a full setup has. A property of the CONTRACT, not of any strategy: the
# chart prints "<met>/<of>", so a strategy scoring out of four just ships of=4 per record.
_MISS_OF = 3


def build_missed_setups(missed: Optional[Sequence[Any]]) -> list[dict]:
    """A strategy's MISSED setups → the lab's missed-setup contract (the price chart's
    "how close did this come" markers).

    A miss is the companion of a block, and a different question. A BLOCKED setup was fully
    ready and a rule refused it. A MISSED setup got partway — it met some of the strategy's
    confluences and then died without ever becoming a trade. Neither places an order, so
    neither exists in any trade list; this is the only channel a miss reaches the lab through.

    Strategy-agnostic in the same way `build_blocked_setups` is: the input is any object
    carrying `dir` / `time_ms` / `edge` / `met` / `near`, parallel `labels` and `reasons`
    sequences, and a `met_lines` list of already-formatted strings
    (`mpc_sos_fade.execution.MissedSetup` satisfies it). Nothing here knows what a
    "confluence" is — `met`/`of` are just a score, and every string is the strategy's own.

    `reasons` is a LIST purely so a miss and a block read identically downstream; a miss has
    exactly one missing piece by construction.
    """
    out: list[dict] = []
    for m in missed or []:
        labels = list(getattr(m, "labels", None) or [])
        texts = list(getattr(m, "reasons", None) or [])
        reasons = [
            {"label": str(labels[i]), "reason": str(texts[i] if i < len(texts) else "")}
            for i in range(len(labels))
        ]
        # The RETRACE this setup was waiting on: when price first reached the zone, and the
        # deepest bar of that visit. A consumer asking "which candle turned it" anchors on those,
        # never on `time_ms` — that is the bar the setup DIED, a median 18 and up to 718 bars
        # later and tens of dollars away. `None` = price never got there, and stays `None`: a zero
        # would read as the epoch, and a fallback to `time_ms` would put the answer back exactly
        # where it was wrong.
        ms = lambda v: int(v) if isinstance(v, (int, float)) else None
        out.append(
            {
                "time_ms": int(getattr(m, "time_ms", 0)),
                "zone_time_ms": ms(getattr(m, "zone_time_ms", None)),
                "zone_turn_ms": ms(getattr(m, "zone_turn_ms", None)),
                "direction": "Long" if getattr(m, "dir", 0) > 0 else "Short",
                "met": int(getattr(m, "met", 0)),
                "of": _MISS_OF,
                # The reader's default view. A strategy marks the misses worth looking at; the ones
                # it doesn't are the ordinary way most setups die, and they are what floods a chart.
                "near": bool(getattr(m, "near", True)),
                "met_lines": [str(s) for s in (getattr(m, "met_lines", None) or [])],
                "reasons": reasons,
                "edge": _round(float(getattr(m, "edge", 0.0)), 5),
            }
        )
    out.sort(key=lambda r: r["time_ms"])
    return out


def build_results(
    trades: Sequence[Any],
    *,
    point_value: float,
    initial_capital: float = 0.0,
    commission_per_side: float = 0.0,
    blocked: Optional[Sequence[Any]] = None,
    missed: Optional[Sequence[Any]] = None,
) -> dict:
    """Everything the lab needs from a finished Python backtest, in one call.

    `blocked` and `missed` are optional and reporting-only — a strategy that records neither
    yields empty lists, and no downstream consumer requires either key.
    """
    trades = list(trades)
    curve = build_equity_curve(trades, initial_capital=initial_capital)
    days = build_daily_pnl(trades)
    return {
        "equity_curve": curve,
        "daily_pnl": days,
        "kpis": build_kpis(
            trades, initial_capital=initial_capital, equity_curve=curve, daily_pnl=days
        ),
        "engine_trades": build_engine_trades(
            trades, point_value=point_value, commission_per_side=commission_per_side
        ),
        "blocked_setups": build_blocked_setups(blocked),
        "missed_setups": build_missed_setups(missed),
    }
