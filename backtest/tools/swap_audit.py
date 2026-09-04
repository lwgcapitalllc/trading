"""swap_audit.py — what does overnight swap actually cost this strategy, and could a stop cover it?

    python backtest/tools/swap_audit.py

**Aaron's question, 2026-08-11**, after `scratch_audit.py` showed the breakeven cohort turning
negative on every real account: *move the stop further into profit at each rollover by the swap
just charged, so a "breakeven" exit is truly zero and a full loss is truly −1R.*

The idea is sound in shape and this measures whether it is worth building. It answers three things
before a line of strategy code is written:

  1. How big is the swap bill, in R, split by direction. Gold CHARGES longs and PAYS shorts, so a
     single net number hides the whole problem.
  2. How far the stop would have to move — per trade, in price — to cover it. Compared against
     `exec_be_buf_tk`, the buffer that is supposed to be doing this job today.
  3. What the fix is worth at its theoretical MAXIMUM: the swap on trades whose stop was already
     staged into profit, which is the only cohort a stop ratchet can rescue without changing which
     trades happen.

⚠ **`puprime_standard` is the tier used, and that choice is what makes the measurement clean.** It
charges $0.00 commission and slippage is 0 in bar mode, so `Trade.costs_usd` on that profile is
**pure swap** with nothing to disentangle. The swap is identical on all three PU Prime tiers
(measured 2026-08-08), so nothing is lost by reading it off this one.

🔴 **Point 3 is an UPPER BOUND, not a forecast, and the distinction has bitten this repo before.**
Moving a stop changes WHEN it triggers, so some trades this rescues would instead stop out earlier
and some that ran on would not. That can only be settled by a replay. The minimum-stop guard was
estimated at +1.84R by exactly this kind of arithmetic and REPLAYED at −1.84R — the cheap estimate
had the sign wrong. **Read this as "the most this could possibly be worth", and if that number is
small, do not build the thing.**
"""

from __future__ import annotations

import argparse
import importlib
import statistics
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_MS_PER_DAY = 86_400_000


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--strategy", default="sos_fade")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2026-08-03")
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--capital", type=float, default=10_000.0)
    args = ap.parse_args(argv)

    from backtest.data.source import BarSource
    from backtest.fills import PROFILES
    from backtest.replay import build_strategy
    from backtest.tools.cost_tiers import _profile_for

    prof = _profile_for("puprime_standard", {"swap"}, None)
    swap = PROFILES["puprime_standard"].swap

    print(f"loading {args.symbol} {args.tf}m  {args.start} -> {args.end} ...", flush=True)
    df = BarSource().load(args.symbol, args.tf, args.start, args.end)
    print(f"  {len(df):,} bars", flush=True)

    mod = importlib.import_module(f"strategies.python.{args.strategy}")
    spec = mod.LAB_STRATEGY
    cfg = spec["config"](fill_model="bar", symbol=args.symbol)
    strat = build_strategy(spec["strategy"], cfg, initial_capital=args.capital, cost_profile=prof)
    strat.run(df, warmup=args.warmup)
    trades = strat.execution.trades

    be_buf = cfg.exec_be_buf_tk * 0.01
    print(
        f"\nswap long {swap.per_lot_per_night(1):+.2f}/lot/night   "
        f"short {swap.per_lot_per_night(-1):+.2f}/lot/night   "
        f"triple on weekday {swap.triple_weekday}"
    )
    print(
        f"  per OUNCE per night: long {swap.per_lot_per_night(1) / swap.contract_size:+.3f}   "
        f"short {swap.per_lot_per_night(-1) / swap.contract_size:+.3f}"
    )
    print(f"  breakeven buffer  exec_be_buf_tk = {cfg.exec_be_buf_tk:.0f} ticks = ${be_buf:.2f}")
    print(
        f"  -> ONE night of long swap is {abs(swap.per_lot_per_night(1) / swap.contract_size) / be_buf:.1f}x "
        f"the whole buffer\n"
    )

    # `costs_usd` on this profile is pure swap — no commission, no slippage. See the docstring.
    print(f"{len(trades)} trades")
    for d, name in ((1, "long"), (-1, "short")):
        side = [t for t in trades if t.dir == d]
        paid = sum(t.costs_usd for t in side)
        in_r = sum(t.costs_usd / t.risk_usd for t in side)
        print(
            f"  {name:6s} n={len(side):<4d} swap total {in_r:+8.2f}R   "
            f"(a NEGATIVE R here is money paid out)"
        )

    total_r = sum(t.costs_usd / t.risk_usd for t in trades)
    print(f"  {'ALL':6s} n={len(trades):<4d} swap total {total_r:+8.2f}R\n")

    # Does each side EARN its swap? The bill on its own says nothing — a cost is only a problem
    # against what it bought, and this strategy holds overnight ON PURPOSE because the runner is
    # where its edge lives. `r` is already NET of swap here, so the gross is r minus the charge.
    print("does each side earn its swap?")
    print(f"  {'':8s} {'n':>4s} {'gross R':>9s} {'swap R':>9s} {'net R':>9s} {'net R/trade':>12s}")
    for d, name in ((1, "long"), (-1, "short")):
        side = [t for t in trades if t.dir == d]
        net = sum(t.r for t in side)
        sw = sum(t.costs_usd / t.risk_usd for t in side)
        print(
            f"  {name:8s} {len(side):>4d} {net - sw:>+9.2f} {sw:>+9.2f} {net:>+9.2f} "
            f"{net / len(side):>+12.3f}"
        )
    print()

    # How far the stop would have to move to cover the swap on each trade. In price units per
    # unit held, which is directly comparable to the buffer.
    print("how far a stop would have to move to cover the swap (price per ounce)")
    print(
        f"  {'':8s} {'n':>4s} {'median':>9s} {'p90':>9s} {'worst':>9s}   vs the ${be_buf:.2f} buffer"
    )
    for d, name in ((1, "long"), (-1, "short")):
        # Only trades that PAID (a credit needs no covering).
        need = sorted(
            -t.costs_usd / t.qty for t in trades if t.dir == d and t.costs_usd < 0 and t.qty > 0
        )
        if not need:
            print(f"  {name:8s} none paid swap — this side is CREDITED")
            continue
        med, p90, worst = (statistics.median(need), need[int(len(need) * 0.9)], need[-1])
        print(
            f"  {name:8s} {len(need):>4d} {med:>9.3f} {p90:>9.3f} {worst:>9.3f}   "
            f"median is {med / be_buf:.1f}x the buffer"
        )

    # The ceiling on what a stop ratchet could recover: the swap paid by trades whose stop had
    # already staged into profit. Those are the ones a ratchet can move without touching a trade
    # that is still genuinely at risk.
    scratch = [t for t in trades if 0 < t.dir * (t.exit_price - t.entry_price) <= be_buf * 1.5]
    paid = [t for t in scratch if t.costs_usd < 0]
    print("\nCEILING on a stage-1 stop ratchet (scratch cohort only)")
    print(f"  {len(scratch)} scratches, {len(paid)} of them paid swap")
    print(
        f"  recoverable at most {-sum(t.costs_usd / t.risk_usd for t in paid):+.2f}R "
        f"over the whole history"
    )
    print("  ⚠ UPPER BOUND. Moving a stop changes when it triggers; only a replay settles it.")
    print("  ⚠ Against this strategy's run-to-run spread of sd 15.06R (jitter_audit.py).")

    # Nights held is what decides whether a FIXED buffer could ever work.
    nights = sorted(max(0, (t.exit_ms - t.entry_ms) // _MS_PER_DAY) for t in trades if t.exit_ms)
    if nights:
        print(
            f"\nnights held: median {statistics.median(nights):.0f}  "
            f"p90 {nights[int(len(nights) * 0.9)]}  max {nights[-1]}"
        )
        print(
            "  A fixed buffer can only be right for one hold length. That is the argument for\n"
            "  ratcheting per rollover rather than widening exec_be_buf_tk."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
