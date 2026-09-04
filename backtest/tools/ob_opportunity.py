#!/usr/bin/env python3
"""ob_opportunity.py — how many setups died for want of a gap, with an ORDER BLOCK sitting there?

Aaron, 2026-08-09, after three order-block runs all measured worse than the shipped FVG rule
(`Order block` 267 trades / +75.93R · `Either` 292 / +85.77R · `FVG first` — all against FVG's
159 / +142.18R):

    "help me analyse how many opportunities are there outside of my winning trades... the ones
    that were three out of three that had no fair value gap — was there an order block I could
    have taken the trade from? What's that count first of all? ... it has to be somewhere within
    61.8 up until 78.6."

**THE HYPOTHESIS THIS EXISTS TO TEST, stated plainly so the result can refute it.** Trading every
order block is bad — measured, twice. That does NOT mean an order block is worthless: those runs
let a block arm setups the FVG rule never armed at all, so they measured a much LARGER and
different population. The question here is narrower and much more interesting: on the setups that
were already fully qualified and died only because no gap was in the zone, was a block there?

⚠ **THIS TOOL COUNTS OPPORTUNITIES. IT DOES NOT MEASURE AN EDGE, AND THE TWO ARE NOT THE SAME.**
A count says how often the case arises. It says nothing about whether taking those trades makes
money — with one position slot a new entry DISPLACES a later one, so even a set of profitable
extras can be a net loss (the Run 12 queue effect, measured). That answer needs a real replay, and
this tool deliberately does not attempt it. What it does is decide whether a replay is worth
running at all: if the count is a handful in eight years, there is nothing to measure.

**THE BAND IS 0.618-0.786, NOT the shipped 0.5-0.886**, because that is what Aaron asked for. Both
are reported side by side, so the cost of the narrowing is visible rather than assumed — the wider
band is what the entry rule actually uses today, and a block that only qualifies there is one
`exec_poi_source` would already have found.

**HOW IT MEASURES.** One replay at the SHIPPED defaults (`exec_poi_source="FVG"`), with the
order-block engine forced ON in the stack. The blocks are therefore TRACKED and never TRADED:
`pois_for` returns `sig.fvgs` alone under "FVG", so the trade list must reproduce the documented
baseline exactly — and it is asserted, not assumed (`--expect-trades`). A run whose baseline moved
would be measuring a different strategy from the one the question is about.

Per bar, for each side, while a setup is alive at stage 2+, it asks THE BAR whether price is in the
retrace band and whether a same-direction block overlaps it. It latches that per setup, and pairs
the latch with the strategy's own `MissedSetup` when one is booked. It does not re-derive the miss
and it does not re-derive the zone visit — both come from the strategy, so this can never disagree
with the lab's own Missed layer about which setups are in question.

⚠ **SAME-DIRECTION blocks only**, matching `signals.pois_for`'s "FVG first" rule: in a long setup a
bearish (supply) block on the entry band is the opposite of confirmation. `--any-direction` counts
both, because that reading was a judgement call and it should be checkable rather than argued.

Usage:
    python backtest/tools/ob_opportunity.py
    python backtest/tools/ob_opportunity.py --start 2020-01-01 --expect-trades 159
    python backtest/tools/ob_opportunity.py --lo 0.5 --hi 0.886 --any-direction
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# The miss code this whole tool is about — `execution._MISS_LABEL[3]` = "No FVG in zone":
# price reached the 0.5-0.886 band and no gap was live while it was there, so there was
# nothing to rest a limit on. Imported by NUMBER with a name check rather than hardcoded
# silently, so a renumbering fails here instead of counting the wrong bucket.
_NO_FVG_CODE = 3


def _fib_price(sig, ratio: float):
    """The price at `ratio` on the leg the strategy is reading THIS bar.

    Priced off the same `fibo_ash` / `fibo_asl` anchors the fiboP* came from, through the
    canonical `fib_level()` — never re-derived from two levels and a direction, which would be a
    second claim about one leg. `None` whenever the fib is inactive, which is the same bar every
    fiboP* is None.
    """
    from engines.fibonacci.geometry import fib_level

    if sig.fibo_ash is None or sig.fibo_asl is None or sig.fibo_dir == 0:
        return None
    return fib_level(sig.fibo_ash, sig.fibo_asl, sig.fibo_dir, ratio)


class _Watch:
    """One side's opportunity latch, opened and reset off the SEQUENCE's own SOS bar.

    It mirrors `execution._MissWatch`'s lifetime deliberately — open at stage 2+, hold until the
    setup dies — so a latch can never describe a different setup from the miss it is paired with.
    """

    __slots__ = ("sos_bar", "bars_in_band", "narrow", "wide", "edge", "n_blocks")

    def __init__(self):
        self.reset(None)

    def reset(self, sos_bar):
        self.sos_bar = sos_bar
        self.bars_in_band = 0
        self.narrow = False  # a block overlapped [lo, hi] while price was in the band
        self.wide = False  # ...and the same for the shipped 0.5-0.886 POI band
        self.edge = None  # where a limit off that block would have rested
        self.n_blocks = 0  # distinct blocks seen qualifying (upper bound — see report)


def _overlaps(a_top, a_bot, b_top, b_bot) -> bool:
    """Inclusive at the edges, matching `signals._zones_overlap` and every band test in the
    strategy. A tolerance here and a strict `>` there is exactly the kind of silent disagreement
    this repo keeps meeting."""
    return min(a_top, b_top) >= max(a_bot, b_bot)


def _scan(watch, sig, is_long: bool, lo_r: float, hi_r: float, any_dir: bool, probe) -> None:
    """One bar of one live setup: was price in the band, and was a block sitting in it?

    ⚠ It asks THE BAR, never a latch. `l_half` / `l_618` are latches — once price tags 0.5 they
    stay true to the leg's death — so driving this off them would count every bar of the setup's
    remaining life as "in the zone" and find a block that arrived long after the retrace was over.
    That is the same defect `_MissWatch.visit` was fixed for on 2026-08-08.
    """
    p2, p6 = sig.fibo_p2, sig.fibo_p6
    if p2 is None or p6 is None:
        return
    band_lo, band_hi = (p2, p6) if p2 <= p6 else (p6, p2)
    if sig.low > band_hi or sig.high < band_lo:
        return  # price is not in the retrace band this bar
    watch.bars_in_band += 1
    probe["band_bars"] += 1

    lo_px, hi_px = _fib_price(sig, lo_r), _fib_price(sig, hi_r)
    if lo_px is None or hi_px is None:
        return
    n_lo, n_hi = (lo_px, hi_px) if lo_px <= hi_px else (hi_px, lo_px)

    for top, bot, is_bull, _born in sig.obs:
        probe["blocks_offered"] += 1
        if not any_dir and is_bull != is_long:
            continue
        probe["blocks_aligned"] += 1
        if _overlaps(top, bot, band_hi, band_lo):
            watch.wide = True
            probe["block_in_wide"] += 1
        if _overlaps(top, bot, n_hi, n_lo):
            if not watch.narrow:
                watch.narrow = True
            watch.n_blocks += 1
            # Where the limit would rest: the shallowest tradeable price of the block, clamped
            # into the band — the SAME clamp `_entry_edges` applies to a gap. Reported so the
            # count can be sanity-checked against a chart, not used for anything.
            e = min(top, band_hi) if is_long else max(bot, band_lo)
            if watch.edge is None or ((e > watch.edge) if is_long else (e < watch.edge)):
                watch.edge = e


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="15")
    ap.add_argument(
        "--start",
        default=None,
        help="YYYY-MM-DD (default: the broker's measured earliest bar at this tf)",
    )
    ap.add_argument("--end", default=None)
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--lo", type=float, default=0.618, help="shallow end of the band to count in")
    ap.add_argument("--hi", type=float, default=0.786, help="deep end of the band to count in")
    ap.add_argument(
        "--any-direction",
        action="store_true",
        help="count a block whichever way it points (default: same-direction only)",
    )
    ap.add_argument(
        "--expect-trades",
        type=int,
        default=None,
        help="assert the run reproduces this trade count — the check that the "
        "order-block engine did not move the baseline it is being measured against",
    )
    args = ap.parse_args(argv)

    from backtest.data.history import floor_for
    from backtest.data.source import BarSource
    from strategies.python.sos_fade import LAB_STRATEGY
    from strategies.python.sos_fade.execution import _MISS_LABEL

    if _MISS_LABEL.get(_NO_FVG_CODE) != "No FVG in zone":
        raise SystemExit(
            f"miss code {_NO_FVG_CODE} is {_MISS_LABEL.get(_NO_FVG_CODE)!r}, not 'No FVG in zone'. "
            f"The codes were renumbered — fix _NO_FVG_CODE before trusting any count here."
        )

    start = args.start
    if start is None:
        fl = floor_for(args.symbol, args.tf)
        if fl is None:
            raise SystemExit(
                f"cannot measure the broker's earliest {args.tf}m history for "
                f"{args.symbol}. Pass --start explicitly rather than guessing one."
            )
        start = fl.isoformat()
    end = args.end or dt.date.today().isoformat()

    print(f"loading {args.symbol} {args.tf}m  {start} -> {end} ...", flush=True)
    df = BarSource().load(args.symbol, args.tf, start, end)
    if df.empty:
        print("no bars returned")
        return 1
    print(f"  {len(df):,} bars  {df.index[0]} -> {df.index[-1]}", flush=True)

    StrategyCls, ConfigCls = LAB_STRATEGY["strategy"], LAB_STRATEGY["config"]
    # The SHIPPED defaults, with two things pinned and both for a stated reason:
    #   exec_poi_source="FVG"  — the run whose misses the question is about. Anything else and
    #                            the blocks would be TRADED, which is the measurement that has
    #                            already been done and come back bad.
    #   exec_secondary=False   — `run()` is primary-only (it never calls step_secondary), so this
    #                            is inert here; it is pinned so the trade count is comparable to
    #                            the documented primary-only baseline rather than coincidentally so.
    cfg = ConfigCls(
        fill_model="bar", symbol=args.symbol, exec_poi_source="FVG", exec_secondary=False
    )
    strat = StrategyCls(config=cfg, initial_capital=args.capital)

    # Force the order-block engine ON while the entry still reads gaps only. This is the whole
    # trick: `stack_config` would leave it OFF under "FVG", so the blocks have to be asked for
    # explicitly. They reach `sig.obs` and nothing reads them — `pois_for` returns `sig.fvgs`.
    stack_cfg = dataclasses.replace(StrategyCls.engine_config(), order_blocks=True)

    from backtest.replay import EngineStack, iter_bars

    stack = EngineStack(strat.stack_config(stack_cfg))
    wl, ws = _Watch(), _Watch()
    hits, misses_seen = [], 0
    # ── THE NON-VACUITY PROBE ────────────────────────────────────────────────────────────
    # A zero from a broken counter and a zero from a real absence are the same character on
    # screen, and the first version of this tool printed a confident 0% for eight years of
    # history because it paired every miss with an already-reset latch. These counters are what
    # separate the two, and the run REFUSES below rather than reporting a zero it cannot stand
    # behind. Same rule as `mt5_link`: "no" and "cannot ask" must never be the same value.
    probe = {
        "block_bars": 0,
        "alive_bars": 0,
        "band_bars": 0,
        "blocks_offered": 0,
        "blocks_aligned": 0,
        "block_in_wide": 0,
    }

    print("  replaying (gaps trade, blocks only watch) ...", flush=True)
    for bar in iter_bars(df):
        state = stack.step(bar)
        sig = strat.signals.update(state)
        seq = strat.sequence.update(sig)
        strat.execution.step(sig, seq)

        if sig.obs:
            probe["block_bars"] += 1

        # ⚠ ORDER IS LOAD-BEARING AND THE FIRST VERSION HAD IT WRONG, silently.
        # A setup DIES on the bar its miss is booked, which means `seq.l_sos_bar` is already
        # None by the time execution.step returns. Resetting the latch before pairing therefore
        # handed every single miss a freshly-blanked watch, and the tool reported a confident
        # ZERO for the whole history. Drain the misses FIRST, against the latch as it stood when
        # the setup was alive; only then re-open for whatever comes next.
        while misses_seen < len(strat.execution.misses):
            m = strat.execution.misses[misses_seen]
            misses_seen += 1
            if m.code != _NO_FVG_CODE:
                continue
            w = wl if m.dir > 0 else ws
            hits.append((m, w.narrow, w.wide, w.edge, w.bars_in_band, w.n_blocks))

        # Open / reset each side's latch off the sequence's own SOS bar, so a brand-new setup
        # never inherits the previous one's blocks.
        for watch, sos in ((wl, seq.l_sos_bar), (ws, seq.s_sos_bar)):
            if sos != watch.sos_bar:
                watch.reset(sos)
        if seq.l_sos_bar is not None:
            probe["alive_bars"] += 1
            _scan(wl, sig, True, args.lo, args.hi, args.any_direction, probe)
        if seq.s_sos_bar is not None:
            probe["alive_bars"] += 1
            _scan(ws, sig, False, args.lo, args.hi, args.any_direction, probe)

    trades = strat.execution.trades
    total_r = sum(t.r for t in trades)
    print(f"\n  {len(trades)} trades / {total_r:+.2f}R   (the run the misses come from)")
    if args.expect_trades is not None and len(trades) != args.expect_trades:
        raise SystemExit(
            f"\nBASELINE MOVED: {len(trades)} trades, expected {args.expect_trades}. Adding the "
            f"order-block engine to the stack was supposed to change NOTHING about what trades — "
            f"if it did, every count below describes a different strategy. Stop and find out why."
        )

    # Refuse before reporting anything, because every number below is a count of things NOT
    # happening, and each of these being zero makes the whole report meaningless in a way the
    # report itself cannot show.
    if probe["block_bars"] == 0:
        raise SystemExit(
            "\nthe order-block engine produced NO live blocks on any bar. It is not "
            "running — every count below would be a fact about the tool, not the "
            "market. Check that stack_config kept order_blocks=True."
        )
    if probe["band_bars"] == 0:
        raise SystemExit(
            "\nno live setup ever had price in its own retrace band. The scan never "
            "ran, so a zero here means nothing."
        )

    by_code: dict[int, int] = {}
    for m in strat.execution.misses:
        by_code[m.code] = by_code.get(m.code, 0) + 1

    band = f"{args.lo:g}-{args.hi:g}"
    dirn = "any-direction" if args.any_direction else "same-direction"
    n = len(hits)
    narrow = [h for h in hits if h[1]]
    wide = [h for h in hits if h[2]]

    print("\n" + "=" * 78)
    print(f"  SETUPS THAT DIED FOR WANT OF A GAP — was a block there?   ({dirn})")
    print("=" * 78)
    print(f"  every miss the strategy booked      {len(strat.execution.misses):>5}")
    for code, cnt in sorted(by_code.items()):
        mark = "  <-- the bucket in question" if code == _NO_FVG_CODE else ""
        print(f"      {_MISS_LABEL.get(code, code):<26} {cnt:>5}{mark}")
    print()
    print(f"  'No FVG in zone' misses             {n:>5}")
    print(
        f"    ...with a block in {band:<14} {len(narrow):>5}   ({100.0 * len(narrow) / n:.0f}%)"
        if n
        else ""
    )
    print(
        f"    ...with a block in 0.5-0.886      {len(wide):>5}   "
        f"({100.0 * len(wide) / n:.0f}%)   <- the band the entry rule uses today"
        if n
        else ""
    )
    print()
    print(f"  for scale: trades the run DID take  {len(trades):>5}")
    print("=" * 78)
    print(
        f"  the scan really ran: {probe['block_bars']:,} bars held a live block · "
        f"{probe['band_bars']:,} bars had a live setup with price in its band"
    )
    print(
        f"  {probe['blocks_offered']:,} block-bars offered, {probe['blocks_aligned']:,} "
        f"{dirn}, {probe['block_in_wide']:,} of those overlapping the 0.5-0.886 band"
    )

    if narrow:
        print(f"\n  the {len(narrow)} in {band}, oldest first:\n")
        print(
            f"  {'when the setup died':<22} {'dir':>4} {'would rest at':>14} {'bars in band':>13}"
        )
        for m, _nw, _wd, edge, bars, _nb in narrow:
            when = dt.datetime.fromtimestamp(m.time_ms / 1000, dt.timezone.utc)
            side = "long" if m.dir > 0 else "short"
            px = f"{edge:.2f}" if edge is not None else "—"
            print(f"  {when:%Y-%m-%d %H:%M} UTC   {side:>5} {px:>14} {bars:>13}")

    print("\n" + "-" * 78)
    print("  READ THIS BEFORE ACTING ON THE NUMBER")
    print("-" * 78)
    print("  A COUNT IS NOT AN EDGE. These are setups where a limit COULD have rested, not")
    print("  trades that would have made money — nothing here knows whether price then came")
    print("  back to touch that limit, where the stop would have sat, or what it made.")
    print("  And with ONE position slot an added entry DISPLACES a later one, so even a")
    print("  profitable set of extras can be a net loss (Run 12's queue effect, measured).")
    print("  The only thing that answers that is a real replay.")
    print()
    print("  The 0.5-0.886 row is the honest control: those blocks are ones `exec_poi_source`")
    print("  already finds today. The gap between the two rows is what the narrower band costs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
