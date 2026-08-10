#!/usr/bin/env python3
"""ob_confluence.py — of the trades A+ ALREADY takes, are the ones whose gap sat on an order
block any better?

Aaron, 2026-08-09, after five order-block angles all measured null or negative (`Order block`
267 trades / +75.93R · `Either` 292 / +85.77R · `FVG first` 276 / +102.90R · a block leg with
its own slot 133 / +0.02R · block presence as a filter, mildly ANTI-predictive) — all against
the shipped FVG rule's 159 / +142.18R:

    "I'm so convinced that there's something there with order blocks, and I can't figure out
    what it is."

**WHY THIS QUESTION IS DIFFERENT FROM THE FIVE THAT FAILED.** Every one of those asked *where do
I put my limit order* — they let a block ARM a setup the gap rule never armed, so each measured a
larger, different population and paid the one-position-slot displacement cost. Run 12 already
priced that cost: with one slot a marginal entry does not ADD to the book, it QUEUES in front of
it, and `Either`'s 178 added trades were +33.08R POSITIVE while the book still came out worst
because it displaced 45 real ones.

This tool adds no trade, removes no trade and moves no entry price. It takes the SAME 159 trades
and splits them in two: the ones whose entry gap overlapped a same-direction live order block, and
the ones whose gap did not. It is a QUALITY question, not an opportunity question — and a quality
split is a risk-sizing lever (Aaron's standing requirement: "I wanna be able to tune how much risk
they can take because some trades are just way higher quality"), which is the one use of a block
that the single position slot cannot punish.

**HOW IT MEASURES.** One replay at the SHIPPED defaults (`exec_poi_source="FVG"`), with the
order-block engine forced ON in the stack, exactly as `ob_opportunity.py` does. Blocks are
therefore TRACKED and never TRADED, so the trade list must reproduce the documented baseline —
asserted via `--expect-trades`, never assumed.

⚠ **THE TAG IS TAKEN FROM THE WINNING GAP, AFTER THE GATES, AT PLACEMENT.** Not from "was a block
anywhere near". A gap only becomes the entry if it overlapped the 0.5-0.886 band AND cleared the
deep-only gate AND cleared the pre-zone gate; the tag asks whether THAT gap — the one the limit
actually rested on — had a same-direction block under it. Anything looser measures a different
claim, and this repo has already been burnt by a latch answering a wider question than the one
asked.

⚠ **THE REPLICA IS PINNED TO THE REAL FUNCTION, WHICH IS THE ONLY REASON IT CAN BE TRUSTED.**
Finding the winning gap means re-running the entry-edge selection, and a second implementation of
a rule is this repo's signature defect. So the replica does not stand alone: every bar it must
reproduce `Execution._entry_edges`'s own edge to the float, and a single disagreement REFUSES the
run rather than reporting a number. A comparator that agrees with itself is not a comparator.

⚠ **SAME-DIRECTION blocks only**, matching `signals.pois_for`'s "FVG first" rule and
`ob_opportunity.py`: in a long setup a bearish (supply) block under the entry is the opposite of
confirmation. `--any-direction` counts both, because that reading was a judgement call and should
be checkable rather than argued.

⚠ **READ THE TOTALS WITH THE BEST TRADE REMOVED.** This strategy is designed fat-tailed — 5 of 165
trades once made 47% of everything won — so a split of 159 trades can be decided by which side one
+27R winner lands on. Both totals are printed with and without each group's single best trade.

Usage:
    python backtest/tools/ob_confluence.py --start 2020-01-01 --expect-trades 159
    python backtest/tools/ob_confluence.py --any-direction
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

# A trade this small either side of flat is the breakeven-stop buffer doing its job, not a
# directional result. Counting it as a "win" is the exact defect the 2026-08-01 KPI audit found on
# the lab's win rate, so the three-way split is reported instead.
_SCRATCH_R = 0.25


def _split(rs):
    """(wins, scratches, losses) at the buffer threshold above."""
    return (sum(1 for r in rs if r > _SCRATCH_R),
            sum(1 for r in rs if -_SCRATCH_R <= r <= _SCRATCH_R),
            sum(1 for r in rs if r < -_SCRATCH_R))


def _mean_sd(rs):
    n = len(rs)
    m = sum(rs) / n
    if n < 2:
        return m, 0.0
    return m, (sum((r - m) ** 2 for r in rs) / (n - 1)) ** 0.5


def _report(name: str, rs) -> None:
    if not rs:
        print(f"  {name:<22} 0 trades")
        return
    tot = sum(rs)
    w, s, l = _split(rs)
    best = max(rs)
    ex = tot - best
    m, sd = _mean_sd(rs)
    print(f"  {name:<22} {len(rs):>4} trades   {tot:>+9.2f}R   avg {m:>+7.3f}R   "
          f"{w:>3}W {s:>3}S {l:>3}L   win {w / len(rs) * 100:>5.1f}%")
    print(f"  {'':<22} {'':>4}          ex-best {ex:>+8.2f}R  (best single trade {best:+.2f}R, "
          f"avg ex-best {ex / max(len(rs) - 1, 1):>+7.3f}R)")
    print(f"  {'':<22} {'':>4}          sd {sd:.3f}R per trade, so the mean carries "
          f"+/-{sd / len(rs) ** 0.5:.3f}R of standard error")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--start", default=None,
                    help="YYYY-MM-DD (default: the broker's measured earliest bar at this tf)")
    ap.add_argument("--end", default=None)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--any-direction", action="store_true",
                    help="a block counts whichever way it points (default: same-direction only)")
    ap.add_argument("--block-tf", default=None,
                    help="read the order blocks from THIS timeframe instead of the trading one "
                         "(e.g. 240 for 4H). The trades never change; only which blocks are asked "
                         "about. Default: the trading timeframe, via the in-stack engine.")
    ap.add_argument("--expect-trades", type=int, default=None,
                    help="assert the run reproduces this trade count — the check that forcing the "
                         "order-block engine on did not move the baseline being measured")
    args = ap.parse_args(argv)

    from backtest.data.history import floor_for
    from backtest.data.source import BarSource
    from strategies.python.mpc_sos_fade import LAB_STRATEGY
    from strategies.python.mpc_sos_fade.signals import _zones_overlap, pois_for

    start = args.start
    if start is None:
        fl = floor_for(args.symbol, args.tf)
        if fl is None:
            raise SystemExit(f"cannot measure the broker's earliest {args.tf}m history for "
                             f"{args.symbol}. Pass --start explicitly rather than guessing one.")
        start = fl.isoformat()
    end = args.end or dt.date.today().isoformat()

    print(f"loading {args.symbol} {args.tf}m  {start} -> {end} ...", flush=True)
    df = BarSource().load(args.symbol, args.tf, start, end)
    if df.empty:
        print("no bars returned")
        return 1
    print(f"  {len(df):,} bars  {df.index[0]} -> {df.index[-1]}", flush=True)

    # ── HIGHER-TIMEFRAME BLOCKS ──────────────────────────────────────────────────────────
    # The trading frame is untouched. A second, coarser frame is replayed through its OWN
    # OrderBlockEngine and its live blocks are what the tag asks about.
    #
    # ⚠ **NO LOOKAHEAD, and this is the whole correctness argument for the mode.** A 4H bar that
    # OPENS before this M15 bar has not happened yet — it is still forming, and its block would be
    # built from candles the strategy cannot have seen. A snapshot is therefore admitted only once
    # its own bar has CLOSED (`open + timeframe <= this bar's close`), which is exactly the rule
    # that makes a higher-timeframe read honest. Get this wrong and the tool manufactures an edge.
    htf_mode = args.block_tf is not None and str(args.block_tf) != str(args.tf)
    snaps: list = []
    cur_blocks: list = []
    if htf_mode:
        import pandas as pd
        from order_blocks import OrderBlockEngine

        print(f"loading block frame {args.symbol} {args.block_tf}m ...", flush=True)
        hdf = BarSource().load(args.symbol, str(args.block_tf), start, end)
        if hdf.empty:
            raise SystemExit(f"no {args.block_tf}m bars for {args.symbol} in this window.")
        step = pd.Timedelta(minutes=int(args.block_tf))
        eng = OrderBlockEngine()   # defaults, matching backtest.replay.stack's own construction
        for i, (ts, row) in enumerate(hdf.iterrows()):
            ev = eng.update(i, float(row.open), float(row.high), float(row.low), float(row.close))
            snaps.append((ts + step,
                          [(b.top, b.bottom, b.is_bullish, b.created_index)
                           for b in (list(ev.active_bull) + list(ev.active_bear))]))
        print(f"  {len(hdf):,} bars, {sum(1 for _t, b in snaps if b):,} of them carrying a live "
              f"block", flush=True)

    def blocks_now(sig):
        """The blocks the tag is asked about on this bar."""
        return cur_blocks if htf_mode else sig.obs

    StrategyCls, ConfigCls = LAB_STRATEGY["strategy"], LAB_STRATEGY["config"]
    # The SHIPPED defaults. `exec_poi_source="FVG"` is the run the question is about — anything
    # else TRADES the blocks, which is the measurement that has already been done five ways.
    # `exec_secondary=False` is inert here (`run()` never calls step_secondary) and is pinned so
    # the count is comparable to the documented primary-only baseline rather than accidentally so.
    cfg = ConfigCls(fill_model="bar", symbol=args.symbol,
                    exec_poi_source="FVG", exec_secondary=False)
    strat = StrategyCls(config=cfg, initial_capital=args.capital)

    if not cfg.exec_req_fvg:
        raise SystemExit("exec_req_fvg is off, so an entry can come from the 0.618 fallback rather "
                         "than from a gap. There is then no 'the gap this trade entered on' to tag.")

    probe = {"bars_with_blocks": 0, "cand": 0, "cand_on_block": 0,
             "placed": 0, "mismatch": 0}
    tags: list = []          # one entry per OPENED position, in open order

    ExecCls = type(strat.execution)

    class _Tagged(ExecCls):
        """Records, per bar and per side, whether the winning entry gap sat on a block.

        Every override calls `super()` FIRST and treats its return as the truth. Nothing here may
        change a decision — the tag is written beside the run, never into it.
        """

        def _entry_edges(self, sig):
            le, se = super()._entry_edges(sig)
            self._tag_l = self._tag_s = None
            c = self._cfg
            p2, p3, p6 = sig.fibo_p2, sig.fibo_p3, sig.fibo_p6
            if None in (sig.fibo_p1, p2, p3, p6, sig.fibo_p7, sig.fibo_p10):
                return le, se
            best_l = best_s = None
            tag_l = tag_s = None
            for top, bot, is_bull, born, _rank in pois_for(c, sig):
                probe["cand"] += 1
                on_ob = any((args.any_direction or od == is_bull)
                            and _zones_overlap(top, bot, ot, ob)
                            for (ot, ob, od, _n) in blocks_now(sig))
                if on_ob:
                    probe["cand_on_block"] += 1
                l_deep_ok = not c.exec_fvg_deep_only or top <= p2
                s_deep_ok = not c.exec_fvg_deep_only or bot >= p2
                pre_ok = self._gap_pre_zone(born, sig)
                if is_bull and sig.fibo_dir == 1 and bot <= p2 and top >= p6 and l_deep_ok and pre_ok:
                    d = self._fib_snap(bot, top, True, sig)
                    e = min(top, p2) if d is None else d
                    if best_l is None or e > best_l:
                        best_l, tag_l = e, on_ob
                if (not is_bull) and sig.fibo_dir == -1 and top >= p2 and bot <= p6 and s_deep_ok and pre_ok:
                    d = self._fib_snap(bot, top, False, sig)
                    e = max(bot, p2) if d is None else d
                    if best_s is None or e < best_s:
                        best_s, tag_s = e, on_ob
            # ── THE PIN ──────────────────────────────────────────────────────────────────
            # The replica exists only to name WHICH gap won. If it ever picks a different price
            # from the real selector, it is picking a different gap, and every tag after that is
            # a guess. Refuse rather than report.
            if best_l != le or best_s != se:
                probe["mismatch"] += 1
                raise SystemExit(
                    f"the tag replica disagrees with Execution._entry_edges at bar {sig.index}: "
                    f"replica long={best_l!r} short={best_s!r} vs real long={le!r} short={se!r}. "
                    f"The entry-edge rule changed and this tool was not updated with it.")
            self._tag_l, self._tag_s = tag_l, tag_s
            return le, se

        def _place_entries(self, sig, seq, dec, long_edge, short_edge) -> None:
            super()._place_entries(sig, seq, dec, long_edge, short_edge)
            # Latched beside the pending order, so a fill hours later is tagged with the gap the
            # limit was PLACED on — not with whatever is live on the fill bar, by which time the
            # gap may be long mitigated.
            self._pl_tag = getattr(self, "_tag_l", None) if self._pend_long else None
            self._ps_tag = getattr(self, "_tag_s", None) if self._pend_short else None
            if self._pend_long or self._pend_short:
                probe["placed"] += 1

        def _open_position(self, pend, fill_price, sig, dec, kind: str = "primary") -> bool:
            opened = super()._open_position(pend, fill_price, sig, dec, kind)
            if opened:
                tags.append(self._pl_tag if pend.dir == 1 else self._ps_tag)
            return opened

    strat.execution.__class__ = _Tagged
    strat.execution._tag_l = strat.execution._tag_s = None
    strat.execution._pl_tag = strat.execution._ps_tag = None

    # Force the order-block engine ON while the entry still reads gaps only. `stack_config` leaves
    # it OFF under "FVG", so the blocks have to be asked for explicitly; they reach `sig.obs` and
    # nothing reads them, because `pois_for` returns `sig.fvgs` alone in this mode.
    stack_cfg = dataclasses.replace(StrategyCls.engine_config(), order_blocks=True)

    from backtest.replay import EngineStack, iter_bars
    stack = EngineStack(strat.stack_config(stack_cfg))

    print("  replaying (gaps trade, blocks only watch) ...", flush=True)
    import pandas as _pd
    bar_step = _pd.Timedelta(minutes=int(args.tf))
    times = list(df.index)
    ptr = 0
    for i, bar in enumerate(iter_bars(df)):
        state = stack.step(bar)
        sig = strat.signals.update(state)
        if htf_mode:
            # Admit every block-frame snapshot whose own bar has already CLOSED by the close of
            # this trading bar. Strictly `<=`: a coarse bar closing on the same instant is
            # information the strategy has when it decides, and one closing later is not.
            close_ts = times[i] + bar_step
            while ptr < len(snaps) and snaps[ptr][0] <= close_ts:
                cur_blocks[:] = snaps[ptr][1]
                ptr += 1
        if blocks_now(sig):
            probe["bars_with_blocks"] += 1
        seq = strat.sequence.update(sig)
        strat.execution.step(sig, seq)

    trades = strat.execution.trades
    print()
    print(f"{len(trades)} trades   {sum(t.r for t in trades):+.2f}R")

    if args.expect_trades is not None and len(trades) != args.expect_trades:
        raise SystemExit(
            f"expected {args.expect_trades} trades, got {len(trades)}. Forcing the order-block "
            f"engine on moved the baseline, so this is no longer a split of the shipped run.")

    # ── NON-VACUITY ──────────────────────────────────────────────────────────────────────
    # A zero from a broken tagger and a zero from a real absence are the same character on screen.
    # Refuse rather than print a confident 0%.
    if probe["bars_with_blocks"] == 0:
        raise SystemExit("no bar in the whole run carried a live order block — the engine was not "
                         "actually on. Every tag below would be a false negative.")
    if probe["cand_on_block"] == 0:
        raise SystemExit("not one gap candidate in the run overlapped a block. That is not "
                         "plausible over this history; the overlap test is broken.")
    if len(tags) != len(trades):
        raise SystemExit(f"tagged {len(tags)} opened positions but the run closed {len(trades)} "
                         f"trades. The open/close pairing this tool assumes does not hold.")
    if any(t is None for t in tags):
        raise SystemExit(f"{sum(1 for t in tags if t is None)} trades opened with no tag recorded. "
                         f"An entry reached a fill without passing through the tagged selector.")

    on = [t.r for t, g in zip(trades, tags) if g]
    off = [t.r for t, g in zip(trades, tags) if not g]

    print()
    print(f"the gap the limit rested on, split by whether a "
          f"{'' if args.any_direction else 'same-direction '}"
          f"{args.block_tf + 'm ' if htf_mode else ''}order block sat under it")
    print(f"  (scratch = |R| <= {_SCRATCH_R})")
    _report("gap ON a block", on)
    _report("plain gap", off)

    # ── IS THE GAP BETWEEN THEM REAL? ────────────────────────────────────────────────────
    # A split of ~160 fat-tailed trades can show a large-looking difference in average R and mean
    # nothing at all. This prints the difference beside the noise on it, so the answer is read off
    # the ratio rather than off the gap. Nothing here is a p-value: the R distribution is nowhere
    # near normal (that is the DESIGN — see the repo's Trading Philosophy), so this is a scale
    # check, and a ratio under ~2 means the two groups are not distinguishable on this history.
    if on and off:
        m_on, sd_on = _mean_sd(on)
        m_off, sd_off = _mean_sd(off)
        se = (sd_on ** 2 / len(on) + sd_off ** 2 / len(off)) ** 0.5
        d = m_on - m_off
        print()
        print(f"  difference (on-block minus plain) {d:+.3f}R per trade, standard error "
              f"{se:.3f}R  ->  {abs(d) / se if se else float('inf'):.2f}x the noise")
        if se and abs(d) / se < 2.0:
            print("  ⚠ under 2x: these two groups are NOT distinguishable on this history. Read "
                  "the direction as a hint at best, never as an edge.")

    print()
    print(f"  candidates seen {probe['cand']:,}  of which on a block {probe['cand_on_block']:,} "
          f"({probe['cand_on_block'] / probe['cand'] * 100:.1f}%)")
    print(f"  bars with a live block {probe['bars_with_blocks']:,} of {len(df):,} "
          f"({probe['bars_with_blocks'] / len(df) * 100:.1f}%)")
    print(f"  bars that placed an order {probe['placed']:,}   replica mismatches {probe['mismatch']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
