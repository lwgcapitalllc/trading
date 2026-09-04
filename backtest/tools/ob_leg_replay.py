#!/usr/bin/env python3
"""ob_leg_replay.py — a REAL replay of the order-block leg, against the shipped bot as control.

`nogap_scalp_audit.py` reconstructs entries off fib geometry so it can price a whole grid. This
runs the order layer. It exists because the audit's best surviving idea turned out to already be
a shipped setting nobody had ever run: the point-of-interest source that rests on an ORDER BLOCK
**only where a gap setup would not have traded at all**. That is exactly the pool the audit was
measuring, and it needs no new code.

⚠ **THREE PIECES OF THE AUDIT'S BEST RULE ARE NOT SETTINGS AND ARE NOT IN THIS RUN.** Say so
rather than letting a reader assume the replay confirms the reconstruction:

  * the limit resting at the **0.5** — the engine's no-gap fallback is hardcoded to the 0.618
    (`_entry_edges`), and the block leg rests on the block's own clamped edge instead;
  * a fixed **2R target** — a primary's rungs are FIB levels (`_place_entries`), not R multiples;
  * the **10:00-12:00 New York** exclusion — the only time gate is the final-hour one.

So this answers *what does the block leg make under the SOS Fade exit rules*, which is a different and
narrower question than *what does a 2R scalp on this pool make*. Building the second one means
code, and it should not be built until this run says the pool is worth it.

⚠ **The basis is IDENTICAL on both rows and that is enforced by construction, not by care** —
one bar frame, one window, one capital, one cost profile, one warmup, both built through
`build_strategy`. Rule 11 has been broken four times in this app and always the same way: the
difference column becomes the thing that lies.

⚠ **Compare R, never the closing dollars** (rule 6). Both legs size off their own balance here,
so a dollar column would compound the better one and read as a bigger edge than it is.

⚠ **The two rows are not additive.** The block leg stands down on any setup a gap ever qualified
for, so it cannot take an SOS Fade trade — but both would run on ONE account with no live allocator, so
their drawdowns can land on top of each other.

Usage:
    python3 backtest/tools/ob_leg_replay.py
    python3 backtest/tools/ob_leg_replay.py --start 2020-01-01 --end 2026-08-06
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_RISKS = (1.0, 2.5, 5.0, 10.0)


def _profile():
    """PU Prime ECN, the tier the live account is on. Commission + swap + one flat spread.

    `bid_ask_fills` is left OFF deliberately: it REPLACES the flat spread charge and moves which
    trades exist, so turning it on here would change the trade list between this tool and every
    stored figure it is being compared against. `spread_or_refuse()` is what makes an unmeasured
    tier fail loudly instead of borrowing Standard's number — ECN is measured, so it answers.
    """
    from backtest.fills import PROFILES

    base = PROFILES["puprime_ecn"]
    return dataclasses.replace(
        base, spread=base.spread_or_refuse(), slippage_ticks=0, bid_ask_fills=False
    )


def _replay(df, warmup: int, capital: float, profile, **overrides):
    from backtest.replay import build_strategy
    from strategies.python.sos_fade import LAB_STRATEGY

    cfg = LAB_STRATEGY["config"](
        fill_model="bar", symbol="XAUUSD", exec_secondary=False, **overrides
    )
    strat = build_strategy(
        LAB_STRATEGY["strategy"], cfg, initial_capital=capital, cost_profile=profile
    )
    strat.run(df, warmup=warmup)
    return strat.execution.trades


def _hours(t) -> float:
    return (t.exit_ms - t.entry_ms) / 3_600_000.0 if t.exit_ms and t.entry_ms else float("nan")


def _overnight(t) -> bool:
    """Did the hold cross a 17:00-New-York rollover? That is the swap boundary, not midnight."""
    from zoneinfo import ZoneInfo

    ny = ZoneInfo("America/New_York")
    a = datetime.fromtimestamp(t.entry_ms / 1000, tz=timezone.utc).astimezone(ny)
    b = datetime.fromtimestamp(t.exit_ms / 1000, tz=timezone.utc).astimezone(ny)
    return (b.date() - a.date()).days > 0 or (a.hour < 17 <= b.hour and a.date() == b.date())


def _summary(name: str, trades) -> dict:
    rs = [t.r for t in trades]
    n = len(rs)
    if not n:
        return {"name": name, "n": 0}
    wins = sum(1 for r in rs if r > 0.05)
    losses = sum(1 for r in rs if r < -0.05)
    scratch = n - wins - losses
    run = peak = 0.0
    dd = 0.0
    streak = worst_streak = 0
    for r in rs:
        run += r
        peak = max(peak, run)
        dd = min(dd, run - peak)
        streak = streak + 1 if r < -0.05 else 0
        worst_streak = max(worst_streak, streak)
    hrs = sorted(h for h in (_hours(t) for t in trades) if h == h)
    over = sum(1 for t in trades if _overnight(t))
    compounded = {}
    for pct in _RISKS:
        eq = hi = 1.0
        low = 0.0
        for r in rs:
            eq *= 1 + pct / 100.0 * r
            if eq <= 0:
                eq = 0.0
                break
            hi = max(hi, eq)
            low = min(low, eq / hi - 1)
        compounded[pct] = (eq, low)
    return {
        "name": name,
        "n": n,
        "r": sum(rs),
        "avg": sum(rs) / n,
        "wins": wins,
        "losses": losses,
        "scratch": scratch,
        "dd": dd,
        "streak": worst_streak,
        "med_hrs": hrs[len(hrs) // 2] if hrs else float("nan"),
        "over": over,
        "comp": compounded,
        "costs": sum(t.costs_usd for t in trades),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2026-08-06")
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--capital", type=float, default=10_000.0)
    args = ap.parse_args(argv)

    from backtest.data.source import BarSource

    print(f"loading {args.symbol} {args.tf}m  {args.start} -> {args.end} ...", flush=True)
    df = BarSource().load(args.symbol, args.tf, args.start, args.end)
    if df.empty:
        print("no bars — is the MT5 agent tunnel up on localhost:8766?")
        return 1
    print(f"  {len(df):,} bars  {df.index[0]} -> {df.index[-1]}", flush=True)
    prof = _profile()
    print(
        f"  costs: {prof.name}  commission ${prof.commission_per_side_per_lot:.2f}/side/lot  "
        f"spread ${prof.spread:.2f}  swap on",
        flush=True,
    )

    rows = []
    for label, ov in (
        ("SOS Fade gap leg (shipped)", {}),
        ("order-block leg (no gap)", {"exec_poi_source": "Order block (no FVG)"}),
    ):
        print(f"replaying {label} ...", flush=True)
        rows.append(_summary(label, _replay(df, args.warmup, args.capital, prof, **ov)))

    W = 100
    print("\n" + "=" * W)
    print(
        f"ORDER-BLOCK LEG vs THE SHIPPED BOT   {args.symbol} {args.tf}m   "
        f"{df.index[0].date()} -> {df.index[-1].date()}"
    )
    print("  identical window, capital, costs, sizing and warmup on both rows")
    print("=" * W)
    print(
        f"\n  {'':<26}{'trades':>7}{'total R':>9}{'R/trade':>9}{'win':>6}{'loss':>6}"
        f"{'scratch':>8}{'worst DD':>10}{'streak':>7}{'med hrs':>9}{'overnight':>10}"
    )
    for s in rows:
        if not s["n"]:
            print(f"  {s['name']:<26}{0:>7}   — traded nothing")
            continue
        print(
            f"  {s['name']:<26}{s['n']:>7}{s['r']:>9.1f}{s['avg']:>9.3f}"
            f"{s['wins']:>6}{s['losses']:>6}{s['scratch']:>8}{s['dd']:>10.1f}"
            f"{s['streak']:>7}{s['med_hrs']:>9.1f}"
            f"{100.0 * s['over'] / s['n']:>9.1f}%"
        )

    print("\n  COMPOUNDED, one leg alone on its own account (R above is the unit-free figure)")
    print(f"  {'':<26}" + "".join(f"{f'at {p}%':>18}" for p in _RISKS))
    for s in rows:
        if not s["n"]:
            continue
        print(
            f"  {s['name']:<26}"
            + "".join(f"{s['comp'][p][0]:>11.2f}x{s['comp'][p][1]:>7.0%}" for p in _RISKS)
        )
    print("\n  ⚠ The two rows cannot be added. Neither leg can take the other's setup, but on ONE")
    print("    account with no live allocator their drawdowns overlap — and that allocator is")
    print("    unbuilt (docs/LIVE_TRADING_PIPELINE.md -> G10).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
