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

__all__ = ["build_results", "build_equity_curve", "build_daily_pnl", "build_kpis",
           "build_engine_trades", "engine_trades_csv"]


def _utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _date(ms: int) -> str:
    return _utc(ms).strftime("%Y-%m-%d")


def _round(x: float, n: int = 2) -> float:
    return round(float(x), n)


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
        curve.append({
            "index":     i,
            "equity":    _round(equity),
            "date":      _date(t.exit_ms),
            "entry_ms":  int(t.entry_ms),
            "direction": "Long" if t.dir > 0 else "Short",
            "profit":    _round(t.pnl_usd),
            "exit_name": t.exit_reason or None,
            "size":      t.qty,
            "favorable": _round(getattr(t, "mfe_usd", 0.0)),
            "adverse":   _round(getattr(t, "mae_usd", 0.0)),
        })
    return curve


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


def build_kpis(trades: Sequence[Any], *, initial_capital: float = 0.0,
               equity_curve: Optional[Sequence[dict]] = None,
               daily_pnl: Optional[Sequence[dict]] = None) -> dict:
    """The KPI dict the lab reads. Keys mirror what the NT8/MT5 paths supply, so
    worthiness/grading/BacktestDetail need no Python-specific branch.

    Sharpe/sortino/cagr are deliberately ABSENT — see the module docstring (the lab
    stamps canonical Sharpe from daily_pnl at completion).
    """
    curve = list(equity_curve if equity_curve is not None
                 else build_equity_curve(trades, initial_capital=initial_capital))
    days = list(daily_pnl if daily_pnl is not None else build_daily_pnl(trades))

    wins   = [t.pnl_usd for t in trades if t.pnl_usd > 0]
    losses = [t.pnl_usd for t in trades if t.pnl_usd < 0]
    gross_profit = sum(wins)
    gross_loss   = abs(sum(losses))
    n = len(trades)

    # PF is undefined with no losses; report it as 0.0 rather than inf so JSON/compare
    # paths stay total-ordered. Worthiness reads PF < 0.8 as DISCARD, so a lossless
    # strategy would be mis-tiered — but that only occurs with a trade count far below
    # every gate anyway (>=30), and inf breaks the JSON encode outright.
    pf = _round(gross_profit / gross_loss, 3) if gross_loss > 0 else 0.0

    durations = [(t.exit_ms - t.entry_ms) / 60000.0 for t in trades]

    return {
        "net_pnl":              _round(sum(t.pnl_usd for t in trades)),
        "gross_profit":         _round(gross_profit),
        "gross_loss":           _round(gross_loss),
        "profit_factor":        pf,
        "trade_count":          n,
        "win_count":            len(wins),
        "loss_count":           len(losses),
        # FRACTION (0.0-1.0), not a percent — the lab-wide convention (sizing_pipeline,
        # metrics regime rows) that every consumer and the frontend's pct() assume.
        "win_rate":             _round(len(wins) / n, 4) if n else 0.0,
        "avg_win":              _round(gross_profit / len(wins)) if wins else 0.0,
        "avg_loss":             _round(-gross_loss / len(losses)) if losses else 0.0,
        "max_drawdown":         _max_drawdown(curve, initial_capital),
        "worst_day_pnl":        _round(min((d["pnl"] for d in days), default=0.0)),
        "worst_losing_streak":  _worst_losing_streak(trades),
        "avg_trade_duration_min": _round(sum(durations) / n, 1) if n else 0.0,
        "total_r":              _round(sum(getattr(t, "r", 0.0) for t in trades), 2),
    }


# ── engine_trades (the runner→sizing-engine contract) ─────────────────────────

_ENGINE_TRADE_COLS = ("index", "entry_time", "exit_time", "direction", "entry_price",
                      "exit_price", "stop_distance", "point_value", "commission_per_side",
                      "exit_reason")


def build_engine_trades(trades: Sequence[Any], *, point_value: float,
                        commission_per_side: float = 0.0) -> list[dict]:
    """Unit-size trade records for `sizing_engine.RawTrade` — the contract that lets a
    Python run flow through the dynamic sizing engine exactly like ORB/LondonBreakout.

    `stop_distance` is why this must come from the STRATEGY and cannot be re-derived from
    a trade export (see RawTrade's docstring): only the strategy knows the 1R it sized
    against. Times are ISO-8601 UTC.
    """
    out: list[dict] = []
    for i, t in enumerate(sorted(trades, key=lambda x: (x.exit_ms, x.entry_ms)), start=1):
        out.append({
            "index":               i,
            "entry_time":          _utc(t.entry_ms).isoformat(),
            "exit_time":           _utc(t.exit_ms).isoformat(),
            "direction":           1 if t.dir > 0 else -1,
            "entry_price":         t.entry_price,
            "exit_price":          t.exit_price,
            "stop_distance":       t.stop_distance,
            "point_value":         point_value,
            "commission_per_side": commission_per_side,
            "exit_reason":         t.exit_reason or "",
        })
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

def build_results(trades: Sequence[Any], *, point_value: float,
                  initial_capital: float = 0.0,
                  commission_per_side: float = 0.0) -> dict:
    """Everything the lab needs from a finished Python backtest, in one call."""
    trades = list(trades)
    curve = build_equity_curve(trades, initial_capital=initial_capital)
    days  = build_daily_pnl(trades)
    return {
        "equity_curve":  curve,
        "daily_pnl":     days,
        "kpis":          build_kpis(trades, initial_capital=initial_capital,
                                    equity_curve=curve, daily_pnl=days),
        "engine_trades": build_engine_trades(trades, point_value=point_value,
                                             commission_per_side=commission_per_side),
    }
