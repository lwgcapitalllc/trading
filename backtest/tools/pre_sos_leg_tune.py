#!/usr/bin/env python3
"""pre_sos_leg_tune.py — what are the best settings for the extreme-leg strategy?

WHY THIS EXISTS AND WHY IT IS NOT THE PARENT STUDY. `pre_sos_leg.py` asked whether the
setup is tradeable at all, and it answered with no position slot — every setup scored on
its own, as though the account could hold all of them at once. `mpc_extreme_leg_strategy.pine`
holds ONE. `pre_sos_leg_queued.py` measured what that costs at the shipped settings
(228 setups -> 200 taken, +0.296R -> +0.276R). This tool sweeps the settings THEMSELVES
with the slot on, because the slot changes which setting wins:

  **an exit that ends a trade sooner is worth more than its average outcome says, because
  it hands the slot back.** A rule scored one-trade-at-a-time cannot see that, and every
  number in the strategy's doc was scored that way.

WHAT "BEST" MEANS HERE, and it is a decision rather than a measurement. Expectancy alone
picks a rule that wins hugely and rarely; total R alone picks whichever rule trades most.
The column that decides what RISK PERCENT is survivable is the worst peak-to-trough run in
multiples of risk, so this reports total R and that drawdown side by side, plus their ratio.

⚠ **Drawdown here assumes a constant risk per trade.** Real sizing compounds, which makes a
good run better and a bad run shallower in percentage terms; the R figure is the honest
neutral one and is what a risk percent should be chosen against.

⚠ **THIS IS A SWEEP, AND A SWEEP FINDS NOISE.** 200 trades over eight years cannot support
a dozen independent decisions. Every knob is moved ONE at a time around the shipped value,
neighbours are printed so a lone spike is visible as a lone spike, and anything that wins is
re-checked on the two halves of the history separately. A setting that only works in one half
is not a setting, it is a story. `CLAUDE.md` -> *Trading Philosophy* is the standing warning:
the honest routes to more trades are another leg, instrument or timeframe, never a looser filter.

Usage:
    python3 backtest/tools/pre_sos_leg_tune.py
    python3 backtest/tools/pre_sos_leg_tune.py --stage exits
"""

from __future__ import annotations

import argparse
import statistics
import sys
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Import the study. Nothing here restates a rule that decides what a setup IS.
from backtest.tools.pre_sos_leg import (  # noqa: E402
    MINUTES,
    Row,
    Signal,
    atr,
    collect,
    drop_coarse,
    load,
    replay_base,
    replay_confirm,
    walk,
    walk_breakeven,
)
from backtest.tools.pre_sos_leg_queued import one_slot, shipped  # noqa: E402

# ⚠ THIS MUST TRACK `mpc_extreme_leg_strategy.pine`'s INPUT DEFAULTS, and it is the one thing here
# that can go stale silently. Every sweep below moves ONE knob away from these, so if they drift
# from the strategy the tool is centred on a configuration nobody runs — and every row still prints
# the word "shipped" while saying it. Changed 2026-08-25 with the file: air under the stop
# 0.05 -> 0.20, take profit the whole swing -> half the way to it.
SHIPPED = {
    "extreme_minutes": 120,
    "swept_minutes": 180,
    "stop_buffer_atr": 0.20,
    "min_r": 2.0,
    "min_families": 1,
    "exit_frac": 0.5,
    "arm_at": None,
}


class Score:
    """One configuration's result, after the one-position rule has been applied."""

    def __init__(self, n: int, wins: int, scratches: int, total: float, dd: float, med_r: float):
        self.n, self.wins, self.scratches = n, wins, scratches
        self.total, self.dd, self.med_r = total, dd, med_r

    @property
    def hit(self) -> float:
        return self.wins / self.n if self.n else 0.0

    @property
    def exp(self) -> float:
        return self.total / self.n if self.n else 0.0

    @property
    def ratio(self) -> float:
        return self.total / self.dd if self.dd > 0 else 0.0

    def row(self, label: str) -> str:
        return (
            f"  {label:26s} n={self.n:4d}  hit={self.hit:5.1%}  exp={self.exp:+.3f}R  "
            f"total={self.total:+7.1f}R  worstDD={self.dd:5.1f}R  R/DD={self.ratio:5.2f}"
        )


def drawdown(rs: Sequence[float]) -> float:
    """Worst peak-to-trough run of the equity curve, in multiples of risk."""
    peak = run = worst = 0.0
    for r in rs:
        run += r
        peak = max(peak, run)
        worst = max(worst, peak - run)
    return worst


def score(
    sigs: Sequence[Signal],
    fast: Sequence[Row],
    horizon: int,
    spread: float,
    exit_frac: float = 1.0,
    arm_at: Optional[float] = None,
) -> Score:
    """Re-book a set of setups under one exit rule, then let a single slot take what it can.

    The exit rule is applied BEFORE the slot, because it changes when each trade ends and
    therefore which later setups are reachable. Doing it the other way round measures a
    strategy that decides its exit after seeing what it missed.
    """
    rebooked: List[Signal] = []
    for s in sigs:
        span = abs(s.target - s.entry)
        tgt = s.entry + s.direction * span * exit_frac
        reward = s.r_available * exit_frac
        if arm_at is None:
            outcome, _, ex = walk(fast, s.i, s.direction, s.entry, s.stop, tgt, horizon)
        else:
            outcome, ex = walk_breakeven(
                fast, s.i, s.direction, s.entry, s.stop, tgt, horizon, arm_at
            )
        rebooked.append(
            Signal(
                i=s.i,
                direction=s.direction,
                year=s.year,
                hour=s.hour,
                entry=s.entry,
                stop=s.stop,
                target=tgt,
                risk=s.risk,
                risk_atr=s.risk_atr,
                r_available=reward,
                outcome=outcome,
                mfe=s.mfe,
                exit_i=ex,
                families=s.families,
                counter_trend=s.counter_trend,
            )
        )

    taken, _ = one_slot(rebooked)
    rs: List[float] = []
    wins = scratches = 0
    for s in taken:
        if s.outcome == "win":
            wins += 1
            rs.append(s.r_available)
        elif s.outcome == "scratch":
            # a scratch is not free: half the spread in, half back out
            scratches += 1
            rs.append(-(spread / 2.0) / s.risk)
        else:
            rs.append(-1.0)
    med = statistics.median([s.r_available for s in taken]) if taken else 0.0
    return Score(len(taken), wins, scratches, sum(rs), drawdown(rs), med)


def collected(fast, base, shifts, a_fast, args, **over) -> List[Signal]:
    """Re-run the study's collection with some knobs moved."""
    ns = Namespace(
        confirm=args.confirm,
        base=args.base,
        spread=args.spread,
        horizon_minutes=args.horizon_minutes,
        entry_on_base_close=False,
        extreme_minutes=over.get("extreme_minutes", SHIPPED["extreme_minutes"]),
        swept_minutes=over.get("swept_minutes", SHIPPED["swept_minutes"]),
        stop_buffer_atr=over.get("stop_buffer_atr", SHIPPED["stop_buffer_atr"]),
    )
    return collect(fast, base, shifts, a_fast, ns)


def half_split(sigs: Sequence[Signal]) -> Tuple[List[Signal], List[Signal]]:
    """Two halves of the history by setup order — the cheapest test that a win is not a story."""
    ordered = sorted(sigs, key=lambda s: s.i)
    mid = len(ordered) // 2
    return ordered[:mid], ordered[mid:]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--broker", default="VantageMarkets_Demo")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--base", default="M15", choices=sorted(MINUTES))
    ap.add_argument("--confirm", default="M5", choices=sorted(MINUTES))
    ap.add_argument("--spread", type=float, default=0.22)
    ap.add_argument("--horizon-minutes", type=int, default=6000)
    ap.add_argument(
        "--stage",
        default="all",
        choices=("all", "filters", "structure", "exits", "stability"),
    )
    args = ap.parse_args()

    base_rows = drop_coarse(load(args.broker, args.symbol, args.base), MINUTES[args.base])
    fast_rows = drop_coarse(load(args.broker, args.symbol, args.confirm), MINUTES[args.confirm])
    print(
        f"{args.base}: {len(base_rows)} bars  "
        f"{datetime.utcfromtimestamp(base_rows[0].ts / 1000):%Y-%m-%d} -> "
        f"{datetime.utcfromtimestamp(base_rows[-1].ts / 1000):%Y-%m-%d}"
    )
    base = replay_base(base_rows)
    shifts = replay_confirm(fast_rows, args.confirm == args.base)
    a_fast = atr(fast_rows)
    horizon = args.horizon_minutes // MINUTES[args.confirm]

    def sc(sigs, **kw) -> Score:
        """Score at the SHIPPED exit rule unless this particular sweep is the one moving it.

        Without this every stage would silently score at the parent study's exit — the whole
        swing — and each knob would be judged against a strategy that is not the one running.
        """
        kw.setdefault("exit_frac", SHIPPED["exit_frac"])
        kw.setdefault("arm_at", SHIPPED["arm_at"])
        return score(sigs, fast_rows, horizon, args.spread, **kw)

    default_pool = collected(fast_rows, base, shifts, a_fast, args)
    default_sigs = shipped(default_pool, SHIPPED["min_r"], SHIPPED["min_families"])
    baseline = sc(default_sigs)
    print("\n=== the shipped settings, with one position ===")
    print(baseline.row("shipped"))

    want = args.stage
    results: Dict[str, Score] = {}

    if want in ("all", "filters"):
        print(f"\n=== how far the target must be, in stops (shipped {SHIPPED['min_r']}) ===")
        for v in (1.5, 2.0, 2.5, 3.0, 3.5, 4.0):
            s = sc(shipped(default_pool, v, SHIPPED["min_families"]))
            results[f"min_r={v}"] = s
            print(s.row(f"target >= {v}"))

        print(f"\n=== how many liquidity levels must agree (shipped {SHIPPED['min_families']}) ===")
        for v in (1, 2, 3):
            s = sc(shipped(default_pool, SHIPPED["min_r"], v))
            results[f"families={v}"] = s
            print(s.row(f"levels >= {v}"))

    if want in ("all", "structure"):
        print(
            f"\n=== how far back the extreme is looked for, minutes (shipped {SHIPPED['extreme_minutes']}) ==="
        )
        for v in (60, 90, 120, 180, 240, 360):
            pool = collected(fast_rows, base, shifts, a_fast, args, extreme_minutes=v)
            s = sc(shipped(pool, SHIPPED["min_r"], SHIPPED["min_families"]))
            results[f"extreme={v}"] = s
            print(s.row(f"extreme {v}m"))

        print(
            f"\n=== how recently a level must have been swept, minutes (shipped {SHIPPED['swept_minutes']}) ==="
        )
        for v in (60, 120, 180, 240, 360, 480):
            pool = collected(fast_rows, base, shifts, a_fast, args, swept_minutes=v)
            s = sc(shipped(pool, SHIPPED["min_r"], SHIPPED["min_families"]))
            results[f"swept={v}"] = s
            print(s.row(f"swept within {v}m"))

        print(f"\n=== air under the stop, in ATR (shipped {SHIPPED['stop_buffer_atr']}) ===")
        for v in (0.0, 0.05, 0.10, 0.20, 0.30, 0.50):
            pool = collected(fast_rows, base, shifts, a_fast, args, stop_buffer_atr=v)
            s = sc(shipped(pool, SHIPPED["min_r"], SHIPPED["min_families"]))
            results[f"buffer={v}"] = s
            print(s.row(f"buffer {v} ATR"))

    if want in ("all", "exits"):
        print(
            f"\n=== take profit part of the way to the swing (shipped {SHIPPED['exit_frac']:.0%}) ==="
        )
        print("    the slot matters here — an earlier exit buys the next setup")
        for v in (0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
            s = sc(default_sigs, exit_frac=v)
            results[f"exit={v}"] = s
            print(s.row(f"exit at {v:.0%} of the way"))

        print("\n=== move the stop to breakeven at (shipped: never) ===")
        for v in (None, 0.3, 0.5, 0.7, 0.9):
            s = sc(default_sigs, arm_at=v)
            label = "never" if v is None else f"{v:.0%}"
            results[f"arm={label}"] = s
            print(s.row(f"breakeven at {label}"))

    if want in ("all", "stability") and results:
        print("\n=== the winners, re-checked on each half of the history ===")
        print("    a setting that only works in one half is not a setting")
        ranked = sorted(results.items(), key=lambda kv: kv[1].total, reverse=True)[:6]
        first, second = half_split(default_sigs)
        for name, _ in ranked:
            kind, _, raw = name.partition("=")
            kw: Dict[str, float] = {}
            pool_a, pool_b = first, second
            if kind == "exit":
                kw = {"exit_frac": float(raw)}
            elif kind == "arm":
                kw = {} if raw == "never" else {"arm_at": float(raw.rstrip("%")) / 100.0}
            elif kind == "min_r":
                pool_a, pool_b = half_split(shipped(default_pool, float(raw), 1))
            elif kind == "families":
                pool_a, pool_b = half_split(shipped(default_pool, 2.0, int(raw)))
            else:
                key = {"extreme": "extreme_minutes", "swept": "swept_minutes"}.get(
                    kind, "stop_buffer_atr"
                )
                val = float(raw) if key == "stop_buffer_atr" else int(raw)
                pool = collected(fast_rows, base, shifts, a_fast, args, **{key: val})
                pool_a, pool_b = half_split(shipped(pool, 2.0, 1))
            a, b = sc(pool_a, **kw), sc(pool_b, **kw)
            print(
                f"  {name:26s} first half {a.exp:+.3f}R ({a.n:3d})   "
                f"second half {b.exp:+.3f}R ({b.n:3d})"
            )


if __name__ == "__main__":
    main()
