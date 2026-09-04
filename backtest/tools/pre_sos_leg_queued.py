#!/usr/bin/env python3
"""pre_sos_leg_queued.py — what survives when only ONE position may be open.

WHY THIS EXISTS. `pre_sos_leg.py` says so in its own docstring: it is a study, not a
backtest, with "no position slot, no queueing". It scores every setup it finds, each on
its own, as though the account could hold all of them at once. `extreme_leg_strategy.pine`
holds exactly one. So the study's setup count is an UPPER BOUND on what the strategy can
take, and the study's expectancy is an average over trades some of which the strategy is
never in a position to enter.

`CLAUDE.md` -> *Trading Philosophy* already records the measured version of this from the
SOS Fade work: with one slot, an extra setup does not ADD to the book, it QUEUES in front of it,
and the loosened runs there displaced 17, 36 and 2 real trades - one displaced winner worth
+16.5R on its own. **That effect has never been measured for this strategy.** This tool
measures it, and it is the honest number to tune against.

WHAT IT DOES, AND WHAT IT IS STILL NOT. It re-runs `pre_sos_leg.py`'s own collection - it
imports it rather than restating any rule, so the two cannot drift - then walks the setups
in time order and takes a setup only when the previous one has been let go. Everything the
parent study is not, this is also not: no sizing, no costs beyond the parent's half-spread,
no news filter, no re-entry cap. It answers ONE question - how much of the reported result
is reachable by a one-position strategy.

FIRST COME, FIRST SERVED, and that is a modelling choice worth naming. A real setup arrives
without knowing whether a better one follows it an hour later, so the strategy cannot skip a
mediocre setup to save the slot. Taking them in order is what the Pine file actually does:
with one position and no pyramiding, a signal arriving mid-trade is ignored outright, not
deferred.

Usage:
    python3 backtest/tools/pre_sos_leg_queued.py
    python3 backtest/tools/pre_sos_leg_queued.py --min-families 2
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Sequence, Tuple

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Import the study rather than restating any part of it. Every rule that decides what a
# setup IS lives there; this file only decides which of them a single slot can reach.
from backtest.tools.pre_sos_leg import (  # noqa: E402
    MINUTES,
    Signal,
    atr,
    collect,
    drop_coarse,
    expectancy,
    load,
    replay_base,
    replay_confirm,
)


def shipped(sigs: Sequence[Signal], min_r: float, min_families: int) -> List[Signal]:
    """The configuration the strategy file actually ships.

    Same three conditions as the study's own headline line: enough room to the target,
    against the higher-frame trend, and at least one liquidity level swept.
    """
    return [
        s
        for s in sigs
        if s.r_available >= min_r and s.counter_trend and len(s.families) >= min_families
    ]


def one_slot(sigs: Sequence[Signal]) -> Tuple[List[Signal], List[Signal]]:
    """Split setups into the ones a single position could take, and the ones it could not.

    A setup entered on bar `i` occupies the slot until `exit_i`. The next setup is reachable
    once the book is flat again - the exit resolves during its own bar, so a setup arriving
    on that same bar's close can still be taken.
    """
    taken: List[Signal] = []
    missed: List[Signal] = []
    free_at = -1
    for s in sorted(sigs, key=lambda x: x.i):
        if s.i >= free_at:
            taken.append(s)
            free_at = s.exit_i
        else:
            missed.append(s)
    return taken, missed


def summarise(label: str, sigs: Sequence[Signal]) -> None:
    if not sigs:
        print(f"  {label:22s} none")
        return
    wins = sum(1 for s in sigs if s.outcome == "win")
    opens = sum(1 for s in sigs if s.outcome == "open")
    total_r = sum(s.r_available if s.outcome == "win" else -1.0 for s in sigs)
    med_r = statistics.median(s.r_available for s in sigs)
    print(
        f"  {label:22s} n={len(sigs):4d}  hit={wins / len(sigs):5.1%}  "
        f"exp={expectancy(sigs):+.3f}R  total={total_r:+8.1f}R  "
        f"medR={med_r:.2f}  unresolved={opens}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--broker", default="VantageMarkets_Demo")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--base", default="M15", choices=sorted(MINUTES))
    ap.add_argument("--confirm", default="M5", choices=sorted(MINUTES))
    ap.add_argument("--spread", type=float, default=0.22)
    ap.add_argument("--min-r", type=float, default=2.0)
    ap.add_argument("--extreme-minutes", type=int, default=120)
    ap.add_argument("--swept-minutes", type=int, default=180)
    ap.add_argument("--horizon-minutes", type=int, default=6000)
    ap.add_argument("--stop-buffer-atr", type=float, default=0.05)
    ap.add_argument(
        "--min-families",
        type=int,
        default=1,
        help="how many liquidity levels must agree - the strategy ships 1",
    )
    # The strategy fills at the 5-minute close, so this stays off. It exists because the
    # parent's collection reads it, and a default that silently differed from the parent's
    # would measure a different thing under the same name.
    ap.add_argument("--entry-on-base-close", action="store_true")
    ap.add_argument("--trigger", default="choch", choices=("choch",))
    ap.add_argument("--reclaim-bars", type=int, default=8)
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
    sigs = shipped(collect(fast_rows, base, shifts, a_fast, args), args.min_r, args.min_families)
    taken, missed = one_slot(sigs)

    print("\n-- the shipped setup, with and without a position slot --")
    summarise("study (no slot)", sigs)
    summarise("strategy (one slot)", taken)
    summarise("could not be taken", missed)

    if sigs:
        print(
            f"\n  {len(missed)} of {len(sigs)} setups ({len(missed) / len(sigs):.1%}) arrive while "
            "the one position is already busy."
        )

    print("\n-- per year (unresolved booked as a full loss) --")
    by_year = defaultdict(lambda: [[], []])
    for s in taken:
        by_year[s.year][0].append(s)
    for s in missed:
        by_year[s.year][1].append(s)
    print(f"     {'year':6s} {'taken':>6s} {'R':>9s}   {'missed':>7s} {'R':>9s}")
    for y in sorted(by_year):
        t, m = by_year[y]
        tr = sum(s.r_available if s.outcome == "win" else -1.0 for s in t)
        mr = sum(s.r_available if s.outcome == "win" else -1.0 for s in m)
        print(f"     {y:<6d} {len(t):6d} {tr:+8.1f}R   {len(m):7d} {mr:+8.1f}R")

    if missed:
        best = max(missed, key=lambda s: s.r_available if s.outcome == "win" else -1.0)
        if best.outcome == "win":
            print(
                f"\n  The single best setup the slot cost: {best.year}, "
                f"{'long' if best.direction > 0 else 'short'}, worth {best.r_available:+.1f}R."
            )


if __name__ == "__main__":
    main()
