"""scratch_audit.py — is a "breakeven" exit actually breakeven, on THIS account?

    python backtest/tools/scratch_audit.py
    python backtest/tools/scratch_audit.py --spread puprime_ecn=0.12 --spread puprime_prime=0.12

**Aaron's question, 2026-08-11.** The stop stages to breakeven **plus `exec_be_buf_tk`** — 30 ticks,
which on gold is **$0.30**. The measured Standard spread is **$0.32**. So the buffer this strategy
calls breakeven is SMALLER than the spread on one of the three accounts, and roughly a quarter of
all trades exit on exactly that stop. **"Are we truly breaking even, or quietly running negative
and calling it flat?"**

**Why this needs its own tool rather than a column on `cost_tiers.py`.** That one answers *what does
a tier cost over 6.5 years*, and a 9R difference spread over 159 trades hides the thing being asked
about here: a cohort that is supposed to net ZERO. A scratch is the one trade type where a few cents
is the entire result, so it has to be looked at on its own or it is averaged into the winners.

⚠ **The spread does NOT appear in `Trade.costs_usd` under `bid_ask_fills`, and reading that field
alone would say a scratch was free.** That model moves the FILL PRICES instead of charging a fee —
which is what a spread really does to a resting limit — so its effect is already inside
`entry_price` and `exit_price` and shows up nowhere else. `costs_usd` carries commission, swap and
slippage only. Both are reported, separately, because adding them would double-count nothing and
explain less.

🔴 **The direction split is the finding this exists to surface, and it is not symmetric.** Broker
bars are the BID. A long's entry is a BUY LIMIT — it fills at the price it names — and its stop is a
SELL, which also transacts at the bid, so a long's scratch pays no spread at all. A SHORT's stop is
a **BUY**, which lifts the ASK: it pays the whole spread on the way out. So a "breakeven" exit is
two different trades depending on which way you were facing, and averaging the two hides it.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_STRATEGIES = {
    "mpc_sos_fade": "strategies.python.mpc_sos_fade",
    "mpc_bleg": "strategies.python.mpc_bleg",
}


def _classify(t, be_buf: float):
    """win / scratch / loss for one trade, decided on the PRICE MOVE, not on the money.

    A scratch is an exit at the breakeven-staged stop: the trade went the right way far enough to
    reach TP1 (which is what stages the stop), then came back and stopped out on that staged level.
    Its gross move is therefore about `+be_buf` per unit.

    ⚠ **Classified on gross price and NOT on `pnl_usd`**, deliberately. Whether a scratch nets
    positive or negative is the QUESTION; using the money to sort them would put the negative ones
    in the "loss" bucket and the answer would come back "all scratches are positive" by
    construction. The cohort has to be defined by what the strategy DID, then measured on what it
    got. Band is 1.5x the buffer, which separates a staged-stop exit from a real target or a real
    stop by an order of magnitude on this instrument.
    """
    gross_per_unit = t.dir * (t.exit_price - t.entry_price)
    if 0 < gross_per_unit <= be_buf * 1.5:
        return "scratch"
    return "win" if gross_per_unit > 0 else "loss"


def _replay(key: str, df, warmup: int, capital: float, profile):
    from backtest.replay import build_strategy

    mod = importlib.import_module(_STRATEGIES[key])
    spec = mod.LAB_STRATEGY
    cfg = spec["config"](fill_model="bar", symbol="XAUUSD")
    strat = build_strategy(spec["strategy"], cfg, initial_capital=capital, cost_profile=profile)
    strat.run(df, warmup=warmup)
    return strat.execution.trades, cfg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strategy", default="mpc_sos_fade", choices=sorted(_STRATEGIES))
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2026-08-03")
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--tier", action="append", default=None)
    ap.add_argument("--spread", action="append", default=None, metavar="TIER=VALUE",
                    help="WHAT-IF spread for one tier, repeatable. Labelled 'stated'. Does not "
                         "touch PROFILES — see cost_tiers.py for the same flag and why.")
    args = ap.parse_args(argv)

    overrides: dict[str, float] = {}
    for item in args.spread or []:
        k, v = item.split("=", 1)
        overrides[k.strip()] = float(v)

    from backtest.data.source import BarSource
    from backtest.fills import PROFILES
    from backtest.tools.cost_tiers import _profile_for

    tiers = args.tier or ["puprime_standard", "puprime_prime", "puprime_ecn"]
    refuses = [t for t in tiers if t not in overrides and not PROFILES[t].spread_measured]
    if refuses:
        raise SystemExit(f"no measured spread for {refuses} — state one with --spread "
                         f"{refuses[0]}=0.12, or measure it. See backtest/fills.py.")

    print(f"loading {args.symbol} {args.tf}m  {args.start} -> {args.end} ...", flush=True)
    df = BarSource().load(args.symbol, args.tf, args.start, args.end)
    print(f"  {len(df):,} bars\n", flush=True)

    layers = {"bid_ask_fills", "swap", "commission"}
    rows = [("free", None)] + [(t, _profile_for(t, layers, overrides.get(t))) for t in tiers]

    for label, profile in rows:
        trades, cfg = _replay(args.strategy, df, args.warmup, args.capital, profile)
        be_buf = cfg.exec_be_buf_tk * 0.01          # ticks -> price on a 2-digit instrument

        spread = "-" if label == "free" else (
            f"${overrides.get(label, PROFILES[label].spread):.2f}"
            + ("*" if label in overrides else ""))
        comm = "-" if label == "free" else f"${PROFILES[label].commission_per_side_per_lot:.2f}"
        print(f"=== {label}   spread {spread}   commission {comm}/side/lot ===")

        buckets: dict[str, list] = {"win": [], "scratch": [], "loss": []}
        for t in trades:
            buckets[_classify(t, be_buf)].append(t)

        print(f"  {'bucket':10s} {'n':>4s} {'mean R':>9s} {'total R':>9s} {'mean $':>10s}"
              f" {'mean costs$':>12s}")
        for name in ("win", "scratch", "loss"):
            b = buckets[name]
            if not b:
                continue
            print(f"  {name:10s} {len(b):>4d} {sum(t.r for t in b)/len(b):>+9.3f} "
                  f"{sum(t.r for t in b):>+9.2f} {sum(t.pnl_usd for t in b)/len(b):>+10.2f} "
                  f"{sum(t.costs_usd for t in b)/len(b):>+12.2f}")

        # The OTHER half of the same question: a full loss is supposed to be exactly -1.000R.
        # Anything past that is risk the account took that nobody authorised, and there are only
        # three ways to get it — the stop gapped (bar mode fills a wrong-side stop at the next
        # open), swap accrued while the trade hung, or commission was charged. Reported as a
        # COUNT and a worst case rather than a mean, because a mean over 50 losses buries the one
        # that ran -1.4R, and it is the tail that builds a drawdown.
        losers = [t for t in buckets["loss"] if t.r < -0.999]
        over = [t for t in losers if t.r < -1.0005]
        if losers:
            print(f"  -> {len(over)} of {len(losers)} full losses are WORSE than -1.000R")
            if over:
                worst = min(over, key=lambda t: t.r)
                excess = sum(-1.0 - t.r for t in over)
                print(f"     worst {worst.r:+.4f}R  costs ${worst.costs_usd:+.2f} on "
                      f"${worst.risk_usd:,.0f} risked   total excess {excess:+.3f}R")

        # The whole question, and the direction split under it.
        s = buckets["scratch"]
        if s:
            neg = [t for t in s if t.pnl_usd < 0]
            print(f"  -> of {len(s)} scratches, {len(neg)} are NET NEGATIVE "
                  f"({100*len(neg)/len(s):.0f}%)")
            for d, name in ((1, "long"), (-1, "short")):
                side = [t for t in s if t.dir == d]
                if not side:
                    continue
                sneg = sum(1 for t in side if t.pnl_usd < 0)
                gross = sum(t.dir * (t.exit_price - t.entry_price) for t in side) / len(side)
                print(f"     {name:6s} n={len(side):<3d} gross/unit {gross:+.3f}  "
                      f"mean R {sum(t.r for t in side)/len(side):+.4f}  "
                      f"mean $ {sum(t.pnl_usd for t in side)/len(side):+.2f}  "
                      f"net negative {sneg}/{len(side)}")
        print()

    if overrides:
        print("  * spread STATED on the command line, not measured off that tier. See "
              "backtest/fills.py.")
    print("  Note: under bid_ask_fills the spread is in the FILL PRICES, not in `mean costs$` —\n"
          "  that column is commission + swap + slippage only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
