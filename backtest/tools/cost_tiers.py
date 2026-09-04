"""cost_tiers.py — replay one strategy under several BROKER ACCOUNT TIERS and compare.

    python backtest/tools/cost_tiers.py
    python backtest/tools/cost_tiers.py --strategy sos_fade --start 2020-01-01
    python backtest/tools/cost_tiers.py --tier puprime_ecn --spread 0.12

**Why this exists.** `docs/LIVE_TRADING_PIPELINE.md` → G5a answers "which PU Prime account type"
with a table of one real replay per row, and that table was produced by hand on 2026-08-06. It has
already needed re-running once, on 2026-08-10, when the raw tiers' spread and commission stopped
being published guesses and became measurements. A measurement nobody can re-run in one command is
a claim, so this is the command.

**Compare the R column, never the closing dollars.** Costs are charged in R terms that are
size-independent (`backtest/reprice.py`'s reasoning), while the dollar balance compounds — so a
cheaper tier shows up in R honestly and in dollars enormously. `command-center/docs/
SHARED_RISK_STACK.md` has the sibling version of this trap written down.

⚠ **`--spread` is a WHAT-IF and is printed as one.** `backtest/fills.py` carries
`SPREAD_UNMEASURED` on any tier nobody has read a spread off, and it REFUSES rather than borrowing
a sibling tier's figure. This flag does not remove that guard and must not be used to sneak a
number past it: it overrides the spread for this run only, and every row it touches is labelled
`stated` instead of `measured`, because a number a human typed into a flag is not a measurement.
Put a figure in `PROFILES` only once it has been read off that tier's own tick stream.

⚠ **`bid_ask_fills` is the model that matters here and it REPLACES the flat spread charge rather
than adding to it.** A flat charge is the market-order intuition, and nothing in these strategies
is a market order — every entry is a resting limit, so a wider quote changes WHETHER an order
fills, not what it fills at. That is why a spread comparison has to be replayed and cannot be
re-priced: the cost acts by removing trades, and a trade that never happened has no P&L to charge.

⚠ **It does NOT report "setups never filled", and that absence is deliberate.** The G5a table has
that column and it is the most informative one there, but nothing in `Execution` counts a resting
order that expired — the figure was produced by hand instrumentation that was not kept. Inventing
a proxy here (say, trades present in the free run and absent under spread) would answer a
different question under the same heading, because with one position slot a refused setup lets a
DIFFERENT setup take the slot: the trade list reshuffles rather than shrinking. Add the counter to
`Execution` if this column is wanted again, and do not derive it from the trade list.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Same registry shape as jitter_audit.py / overlap_audit.py / run_report.py — a package that
# declares LAB_STRATEGY runs here for free. Keep them in step when a third Python strategy lands.
_STRATEGIES = {
    "sos_fade": "strategies.python.sos_fade",
    "b_leg": "strategies.python.b_leg",
}


def _replay(key: str, df, warmup: int, capital: float, profile):
    """One full replay. Goes through `build_strategy` because this tool always states costs.

    Constructing the class directly is the defect `backtest/replay/build.py` exists to refuse: a
    strategy that cannot accept a `cost_profile` would silently run FREE while this table
    presented its row as charged, which is the exact shape of the lab's months-long frictionless
    bug. Here it would be worse than silent — it would be a cost comparison with an uncharged row
    in it.
    """
    from backtest.replay import build_strategy

    mod = importlib.import_module(_STRATEGIES[key])
    spec = mod.LAB_STRATEGY
    cfg = spec["config"](fill_model="bar", symbol="XAUUSD")
    strat = build_strategy(spec["strategy"], cfg, initial_capital=capital, cost_profile=profile)
    strat.run(df, warmup=warmup)
    return strat.execution.trades


def _profile_for(tier: str, layers: set[str], spread_override: float | None):
    """Build the `AccountProfile` for one row, or return None for the free control.

    Mirrors `command-center/backend/services/python_runner.py::_cost_profile` rather than
    reimplementing the cost model — the layer names and the bid/ask-replaces-spread rule are that
    module's contract, and two answers about what a layer charges is how the lab and this tool
    would drift apart while both looking right.
    """
    import dataclasses

    from backtest.fills import PROFILES

    if not layers:
        return None
    base = PROFILES[tier]
    bid_ask = "bid_ask_fills" in layers
    spread = 0.0
    if "spread" in layers or bid_ask:
        # `spread_or_refuse()` is what makes an unmeasured tier fail loudly instead of borrowing
        # Standard's number. Only an EXPLICIT override may step around it, and the caller has to
        # have typed it.
        spread = base.spread_or_refuse() if spread_override is None else spread_override
    # `replace` rather than a fresh constructor on purpose: every field this tool does not name —
    # contract size, mintick, latency — is a property of the real account and must travel
    # untouched. Re-listing them here would mean a field added to `AccountProfile` silently
    # reverts to its default in this tool alone, which is how a cost table quietly stops matching
    # the lab it is meant to agree with.
    return dataclasses.replace(
        base,
        name=f"tier:{tier}",
        commission_per_side_per_lot=(
            base.commission_per_side_per_lot if "commission" in layers else 0.0
        ),
        swap=base.swap if "swap" in layers else None,
        slippage_ticks=0,
        spread=spread,
        bid_ask_fills=bid_ask,
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--strategy", default="sos_fade", choices=sorted(_STRATEGIES))
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="15")
    ap.add_argument(
        "--start",
        default="2020-01-01",
        help="YYYY-MM-DD. The G5a table's window starts here; keep it to compare.",
    )
    ap.add_argument("--end", default="2026-08-03")
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument(
        "--tier",
        action="append",
        default=None,
        help="a broker profile name, repeatable (default: the three PU Prime tiers)",
    )
    # Per-TIER and not one global number, because the tiers differ by exactly this figure — a
    # single --spread applied to every row would quietly hand Standard the raw tiers' quote and
    # produce a table whose whole subject had been flattened out of it.
    ap.add_argument(
        "--spread",
        action="append",
        default=None,
        metavar="TIER=VALUE",
        help="WHAT-IF spread for one tier, repeatable (e.g. puprime_ecn=0.12). "
        "Labelled 'stated', never 'measured'. Does not touch PROFILES.",
    )
    args = ap.parse_args(argv)

    overrides: dict[str, float] = {}
    for item in args.spread or []:
        if "=" not in item:
            raise SystemExit(f"--spread wants TIER=VALUE, got {item!r}")
        k, v = item.split("=", 1)
        overrides[k.strip()] = float(v)

    from backtest.data.source import BarSource
    from backtest.fills import PROFILES, SPREAD_UNMEASURED

    tiers = args.tier or ["puprime_standard", "puprime_prime", "puprime_ecn"]
    unknown = [t for t in tiers if t not in PROFILES]
    if unknown:
        raise SystemExit(f"unknown tier(s) {unknown} — known: {sorted(PROFILES)}")

    # Refuse an unmeasured spread BEFORE any bars are loaded or replayed. `spread_or_refuse()`
    # would raise anyway — but at the first CHARGE, i.e. after the free control has already run a
    # full 155k-bar replay, so the same correct refusal arrives minutes later having burned the
    # work it was meant to prevent. Same reasoning as the optimizer's grid-size guard: check from
    # the cheap fact, not from the expensive one.
    refuses = [t for t in tiers if t not in overrides and not PROFILES[t].spread_measured]
    if refuses:
        raise SystemExit(
            f"no measured spread for {refuses} — this table charges the spread on every tier, and "
            f"a tier's spread is deliberately NOT defaulted to a sibling's (see fills.py). Either "
            f"state one for this run (e.g. --spread {refuses[0]}=0.12, labelled 'stated' in the "
            f"output) or measure it with algos/tools/broker_facts.py --history-days 1."
        )

    print(f"loading {args.symbol} {args.tf}m  {args.start} -> {args.end} ...", flush=True)
    df = BarSource().load(args.symbol, args.tf, args.start, args.end)
    if df.empty:
        raise SystemExit("no bars returned")
    print(f"  {len(df):,} bars  {df.index[0]} -> {df.index[-1]}\n", flush=True)

    # The free control is not decoration. Without it a tier's R has nothing to be a delta OF, and
    # the whole point of the table is the gap rather than the level.
    rows = [("free", "-", "-", set())]
    for t in tiers:
        rows.append((t, "-", "-", {"bid_ask_fills", "swap", "commission"}))

    results = []
    for tier, _, _, layers in rows:
        profile = _profile_for(tier if tier != "free" else tiers[0], layers, overrides.get(tier))
        label = tier
        if layers:
            base = PROFILES[tier]
            stated = tier in overrides
            spread = overrides[tier] if stated else base.spread
            src = "stated" if stated else ("measured" if spread != SPREAD_UNMEASURED else "REFUSED")
            comm = base.commission_per_side_per_lot
            print(
                f"replaying {label:18s} spread ${spread:.2f} ({src})  "
                f"commission ${comm:.2f}/side/lot ...",
                flush=True,
            )
        else:
            print(f"replaying {label:18s} no costs ...", flush=True)
        trades = _replay(args.strategy, df, args.warmup, args.capital, profile)
        total_r = sum(t.r for t in trades)
        results.append((label, len(trades), total_r, tier in overrides))
        print(f"  {len(trades)} trades  {total_r:+.2f}R", flush=True)

    free_r = results[0][2]
    print(f"\n{'tier':20s} {'trades':>7s} {'total R':>10s} {'vs free':>10s}  source")
    for label, n, r, stated in results:
        delta = "-" if label == "free" else f"{r - free_r:+.2f}"
        src = "-" if label == "free" else ("SPREAD STATED" if stated else "measured")
        print(f"{label:20s} {n:>7d} {r:>+10.2f} {delta:>10s}  {src}")

    if overrides:
        for k, v in overrides.items():
            print(
                f"\n  ⚠ {k} spread ${v:.2f} was STATED on the command line, not measured off "
                f"that tier's\n    own tick stream. It is not in `backtest/fills.py` and this "
                f"run does not put it there."
            )
    print(
        "\n  ⚠ Read the R column, not a balance. Costs are size-independent in R; dollars "
        "compound.\n  ⚠ This strategy's run-to-run spread is sd 15.06R (jitter_audit.py), so a "
        "gap smaller\n    than that is not an edge — it is noise wearing a decimal point."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
