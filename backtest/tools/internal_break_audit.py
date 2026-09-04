#!/usr/bin/env python3
"""internal_break_audit.py — does an INTERNAL break against the trade predict a bad entry?

Aaron's observation, 2026-08-23, made from the price chart on a losing re-entry:

    "if price creates an internal break of structure, don't take the trade. In this case price
     wicked really deep, triggered the entry and printed an internal break of structure. As soon
     as price goes positive we should just get out of the trade — because it never gets a TP1
     in that case."

CONFIRMED on that trade before this tool was written: the A+ primary long of 2025-08-18 13:30
was preceded by a BEARISH internal break at 13:00 — one bar earlier — and it lost a full -1R
having never touched TP1 (best price 3340.11 against a 3345.07 rung).

This tool asks whether that generalises, and it asks it two ways, because the observation is
really two different rules:

    RULE A — DO NOT TAKE IT.       An against-direction internal break inside the window before
                                   entry means the setup is refused.
    RULE B — GET OUT AT FLAT.      Take it, but the moment price trades back through the entry,
                                   leave. A flagged trade becomes a scratch instead of a loss —
                                   and instead of a win, when it was going to be one.

🔴 **THIS IS A STATIC RE-SCORE OF ONE BOOK, NOT A REPLAY, AND THE DIFFERENCE IS LOAD-BEARING.**
Both rules are applied to the trades the strategy ACTUALLY took, so nothing here can see the two
things a real replay would:

  * **The freed position slot.** This strategy holds one position at a time, so refusing a setup
    does not merely remove its R — it lets whatever queued behind it trade instead. The repo has
    already MEASURED that effect running the other way (root CLAUDE.md, Run 12: loosening the
    entry displaced 17, 36 and 2 real trades, one of them worth +16.5R on its own). Refusing
    setups will displace trades too, and the sign is not knowable from here.
  * **Compounding.** Every figure below is in R for that reason — a dollar answer off a
    re-scored book would be describing an account that never existed.

So read this as *is the signal worth implementing*, never as *this is what the rule makes*. If
it looks worth it, the next step is a config flag and a real replay, which is the only thing
that can answer the second question.

⚠ **`exec_secondary` is PINNED OFF and this is a single-stream replay** — the re-entry needs
`run_dual` and a second bar frame, and replaying single-stream with it on silently returns a
primary-only book. So this measures the PRIMARY book, while the trade that prompted it was a
re-entry. Said out loud rather than left for a reader to assume the answer covers both.

⚠ **Costs are not charged.** Every comparison here is between two readings of the same trades,
so a cost charged to both sides cancels — but "went positive" is measured on the raw price, and
a real exit at flat pays the spread. Rule B's scratch is therefore slightly optimistic.

⚠ **Internal structure is read from a SECOND pass of the engine stack**, built from the
strategy's own `stack_config`, rather than by threading a hook through the strategy. The stack is
deterministic on the same frame, so the two passes see the same bars — and the strategy stays
untouched, which is what keeps its parity gate meaningful.

⚠ **`show_internal=False` on this strategy does NOT hide these events.** That flag only stops the
Structure fib adopting an internal swing as its anchor; `structure.internal` is computed on every
bar regardless. So the rule below is readable today without changing what the strategy trades.

Usage:
    python backtest/tools/internal_break_audit.py --start 2020-01-01 --end 2026-08-23
"""

from __future__ import annotations

import argparse
import dataclasses
import statistics
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_STRATEGIES = {
    "sos_fade": "strategies.python.sos_fade",
    "b_leg": "strategies.python.b_leg",
}

# The windows tested, in bars BEFORE the entry bar, inclusive of the entry bar itself. 0 means
# "the entry bar only". They are a range rather than one pick because the observation names no
# window — it names a chart — and which window discriminates is the thing being measured.
_WINDOWS = (0, 1, 3, 5, 10, 20)


def _pct(n: int, total: int) -> str:
    return f"{(100.0 * n / total):5.1f}%" if total else "    -"


def _touched(trade, target: float) -> bool:
    """Did the hold's best price ever reach this rung? A rung of 0.0 was never frozen and reads
    as untouched — an unset target must not read as one that was hit."""
    if not target:
        return False
    return trade.mfe_price >= target if trade.dir > 0 else trade.mfe_price <= target


def _stats(rows: list) -> str:
    if not rows:
        return "   -"
    rs = [r["r"] for r in rows]
    wins = sum(1 for r in rs if r > 0.15)
    tp1 = sum(1 for r in rows if r["tp1_touched"])
    return (
        f"R sum {sum(rs):>8.2f}   mean {statistics.fmean(rs):>6.3f}"
        f"   median {statistics.median(rs):>6.3f}   won {_pct(wins, len(rs))}"
        f"   reached TP1 {_pct(tp1, len(rows))}"
    )


def _replay(StrategyCls, cfg, capital, df, warmup, mode, sos_too):
    """One replay of the whole book with the internal-break veto applied AT THE FILL.

    🔴 **This re-implements the six lines of `SosFadeStrategy.run` and that is a real risk** —
    a second driver that drifts from the strategy's own would answer a question about a strategy
    nobody trades. It is guarded rather than trusted: `mode=None` runs the identical loop with the
    veto switched off, and the caller asserts it reproduces `run()`'s book exactly before believing
    any vetoed number beside it. A duplicate that is proven byte-identical on the null case is the
    cheapest honest version of this; threading a hook through the strategy would change a file
    whose parity gate is the reason the live bot is trusted.

    The veto refuses the FILL, which is the only place a setup becomes a position:

      * `bar`   — the vetoed side's resting order is withheld for this bar only. The order is
                  re-placed at the close as usual, so a setup whose break printed on the wick can
                  still fill a bar later. This is the literal reading of *do not take it here*.
      * `setup` — the side stays blocked for as long as the sequence keeps the same SOS bar, i.e.
                  for the rest of that setup. This is the reading of *do not take this trade*.
    """
    from backtest.replay import EngineStack, iter_bars

    strat = StrategyCls(config=cfg, initial_capital=capital)
    if len(df.index) > 1:
        strat.execution.bar_ms = int(df.index.to_series().diff().min().total_seconds() * 1000)

    ex = strat.execution
    real_fill = ex._try_entry_fill
    state = {"veto_l": False, "veto_s": False}

    def gated(sig, dec):
        held_l, held_s = None, None
        if state["veto_l"]:
            held_l, ex._pend_long = ex._pend_long, None
        if state["veto_s"]:
            held_s, ex._pend_short = ex._pend_short, None
        try:
            return real_fill(sig, dec)
        finally:
            # Restored rather than dropped: Phase B re-places from this bar's close either way, and
            # leaving the attribute nulled would be a second, invisible edit to the order book.
            if held_l is not None:
                ex._pend_long = held_l
            if held_s is not None:
                ex._pend_short = held_s

    ex._try_entry_fill = gated

    blocked_l_sos, blocked_s_sos = None, None
    stack = EngineStack(strat.stack_config(None))
    for bar in iter_bars(df):
        bar_state = stack.step(bar)
        ev = bar_state.structure.internal
        bear = ev.bear_bos or (sos_too and ev.bear_sos)
        bull = ev.bull_bos or (sos_too and ev.bull_sos)

        sig = strat.signals.update(bar_state)
        seq = strat.sequence.update(sig)

        if mode is None:
            state["veto_l"] = state["veto_s"] = False
        elif mode == "bar":
            state["veto_l"], state["veto_s"] = bear, bull
        else:  # setup
            if bear:
                blocked_l_sos = seq.l_sos_bar
            if bull:
                blocked_s_sos = seq.s_sos_bar
            # A block dies with the setup it was written against: `l_sos_bar` is the identity of
            # the live sequence, so a new one (or none at all) clears it. Without this the side
            # would stay blocked for the rest of the run.
            if blocked_l_sos is not None and seq.l_sos_bar != blocked_l_sos:
                blocked_l_sos = None
            if blocked_s_sos is not None and seq.s_sos_bar != blocked_s_sos:
                blocked_s_sos = None
            state["veto_l"] = blocked_l_sos is not None
            state["veto_s"] = blocked_s_sos is not None

        dec = strat.execution.step(sig, seq)
        if bar.index >= warmup:
            strat.decisions.append(dec)

    strat.finalize(df)
    return strat.execution.trades


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Internal break against the trade — is it a filter?")
    ap.add_argument("--strategy", default="sos_fade", choices=sorted(_STRATEGIES))
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument(
        "--replay",
        choices=("bar", "setup"),
        help=(
            "run RULE A as a real replay instead of a static re-score, so the freed position "
            "slot is included. 'bar' refuses the fill only on a flagged bar (the order stays "
            "resting and may fill later); 'setup' blocks that side for the rest of the setup."
        ),
    )
    ap.add_argument(
        "--sos-too",
        action="store_true",
        help="count an internal CHANGE OF CHARACTER (iSOS) as a break as well as an iBOS",
    )
    args = ap.parse_args(argv)

    import datetime as dt
    import importlib

    from backtest.data.source import BarSource
    from backtest.replay import EngineStack, iter_bars

    mod = importlib.import_module(_STRATEGIES[args.strategy])
    spec = mod.LAB_STRATEGY
    StrategyCls, ConfigCls = spec["strategy"], spec["config"]

    end = args.end or dt.date.today().isoformat()
    print(f"loading {args.symbol} {args.tf}m  {args.start} -> {end} ...", flush=True)
    df = BarSource().load(args.symbol, args.tf, args.start, end)
    if df.empty:
        print("no bars returned — is the MT5 agent tunnel up on localhost:8766?")
        return 1
    print(f"  {len(df):,} bars  {df.index[0]} -> {df.index[-1]}", flush=True)

    cfg = ConfigCls(fill_model="bar", symbol=args.symbol)
    if hasattr(cfg, "exec_secondary"):
        cfg = dataclasses.replace(cfg, exec_secondary=False)  # see the module docstring

    print(f"replaying {args.strategy} (warmup {args.warmup}) ...", flush=True)
    strat = StrategyCls(config=cfg, initial_capital=args.capital)
    strat.run(df, warmup=args.warmup)
    trades = strat.execution.trades
    if not trades:
        print("no trades in this window.")
        return 1

    print("second pass for internal structure ...", flush=True)
    # bar index -> was there a BEARISH / BULLISH internal break on it
    bear_at: set[int] = set()
    bull_at: set[int] = set()
    stack = EngineStack(strat.stack_config(None))
    for bar in iter_bars(df):
        ev = stack.step(bar).structure.internal
        if ev.bear_bos or (args.sos_too and ev.bear_sos):
            bear_at.add(bar.index)
        if ev.bull_bos or (args.sos_too and ev.bull_sos):
            bull_at.add(bar.index)

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()

    rows = []
    for t in trades:
        against = bear_at if t.dir > 0 else bull_at
        # The window is [entry - n, entry] INCLUSIVE of the entry bar: the observation is that the
        # break printed on the wick that filled the order, so excluding the entry bar would exclude
        # the case that prompted this.
        flags = {n: any((t.entry_index - k) in against for k in range(0, n + 1)) for n in _WINDOWS}
        # …and after the fill, while the trade was still open and had not yet reached TP1.
        after = any(i in against for i in range(t.entry_index + 1, t.exit_index + 1))

        # RULE B needs the first bar the trade was ever in profit, and it has to be a bar the trade
        # was STILL OPEN on. `mfe_price` cannot answer it: it is the best price over the hold with
        # no bar attached, so a trade whose only positive tick was on its stop-out bar would read as
        # exitable. Bars strictly before the exit are unambiguous; the exit bar itself is not
        # (intrabar order is unknown), so it is counted separately and reported.
        flat_bar = None
        for i in range(t.entry_index + 1, t.exit_index):
            if (highs[i] >= t.entry_price) if t.dir > 0 else (lows[i] <= t.entry_price):
                flat_bar = i
                break
        rows.append(
            {
                "t": t,
                "r": t.r,
                "tp1_touched": _touched(t, t.tp1),
                "flags": flags,
                "after": after,
                "flat_bar": flat_bar,
            }
        )

    total = len(rows)
    base_r = sum(r["r"] for r in rows)
    print()
    print("=" * 108)
    print(f"{args.strategy}  ·  {total} trades  ·  {df.index[0].date()} -> {df.index[-1].date()}")
    print(f"break = internal BOS{' or iSOS' if args.sos_too else ''} AGAINST the trade direction")
    print("=" * 108)
    print(f"  BASELINE (as traded)               {total:>4}  100.0%   {_stats(rows)}")
    print()

    print("── SPLIT BY WINDOW — a break in the N bars up to and including the entry bar ──")
    for n in _WINDOWS:
        hit = [r for r in rows if r["flags"][n]]
        miss = [r for r in rows if not r["flags"][n]]
        label = "entry bar only" if n == 0 else f"entry bar + {n} before"
        print(f"  {label:<24} flagged {len(hit):>4}  {_pct(len(hit), total)}   {_stats(hit)}")
        print(f"  {'':<24} clean   {len(miss):>4}  {_pct(len(miss), total)}   {_stats(miss)}")
    print()

    aft = [r for r in rows if r["after"]]
    print("── A break that printed AFTER the fill, while the trade was open ──")
    print(f"  {'flagged':<24}         {len(aft):>4}  {_pct(len(aft), total)}   {_stats(aft)}")
    print(
        f"  {'clean':<24}         {total - len(aft):>4}  {_pct(total - len(aft), total)}"
        f"   {_stats([r for r in rows if not r['after']])}"
    )
    print()

    print("── RULE A — refuse the setup (static: the freed slot is NOT modelled) ──")
    for n in _WINDOWS:
        kept = [r for r in rows if not r["flags"][n]]
        dropped = total - len(kept)
        new_r = sum(r["r"] for r in kept)
        label = "entry bar only" if n == 0 else f"entry bar + {n} before"
        print(
            f"  {label:<24} refuse {dropped:>4}   R {base_r:>8.2f} -> {new_r:>8.2f}"
            f"   ({new_r - base_r:+8.2f})"
        )
    print()

    print("── RULE B — take it, leave the moment it is flat (static) ──")
    print("   a flagged trade books 0R once price traded back through the entry, else it keeps")
    print("   its real result. Trades that only went positive on their own exit bar are NOT")
    print("   counted as exitable — that bar's intrabar order is unknown.")
    for n in _WINDOWS:
        new_r, saved, gave_up, stuck = 0.0, 0, 0, 0
        for r in rows:
            if r["flags"][n] and r["flat_bar"] is not None:
                new_r += 0.0
                if r["r"] < 0:
                    saved += 1
                elif r["r"] > 0:
                    gave_up += 1
            else:
                new_r += r["r"]
                if r["flags"][n]:
                    stuck += 1
        label = "entry bar only" if n == 0 else f"entry bar + {n} before"
        print(
            f"  {label:<24} R {base_r:>8.2f} -> {new_r:>8.2f}   ({new_r - base_r:+8.2f})"
            f"   losses saved {saved:>3}   winners given up {gave_up:>3}   never flat {stuck:>3}"
        )
    print()

    print("── RULE B applied to the AFTER-THE-FILL break instead ──")
    new_r, saved, gave_up, stuck = 0.0, 0, 0, 0
    for r in rows:
        if r["after"] and r["flat_bar"] is not None:
            if r["r"] < 0:
                saved += 1
            elif r["r"] > 0:
                gave_up += 1
        else:
            new_r += r["r"]
            if r["after"]:
                stuck += 1
    print(
        f"  {'break while open':<24} R {base_r:>8.2f} -> {new_r:>8.2f}   ({new_r - base_r:+8.2f})"
        f"   losses saved {saved:>3}   winners given up {gave_up:>3}   never flat {stuck:>3}"
    )
    if args.replay:
        print("── RULE A as a REAL REPLAY — the freed position slot IS included ──")
        print("   self-check first: the same loop with the veto OFF must reproduce the book above.")
        null_trades = _replay(StrategyCls, cfg, args.capital, df, args.warmup, None, args.sos_too)
        null_r = sum(t.r for t in null_trades)
        ok = len(null_trades) == total and abs(null_r - base_r) < 1e-9
        print(
            f"   veto off: {len(null_trades):>4} trades   R {null_r:>8.2f}"
            f"   {'MATCHES the baseline' if ok else 'DOES NOT MATCH — every number below is void'}"
        )
        if not ok:
            return 1
        vetoed = _replay(StrategyCls, cfg, args.capital, df, args.warmup, args.replay, args.sos_too)
        v_r = sum(t.r for t in vetoed)
        v_rows = [{"r": t.r, "tp1_touched": _touched(t, t.tp1)} for t in vetoed]
        print(
            f"   veto '{args.replay}': {len(vetoed):>4} trades   R {base_r:>8.2f} -> {v_r:>8.2f}"
            f"   ({v_r - base_r:+8.2f})"
        )
        print(f"   {'':<12} {_stats(v_rows)}")
        print(
            f"   trade count {total} -> {len(vetoed)}"
            f"   ({len(vetoed) - total:+d}; a refused setup frees the slot, so this is NOT"
            f" minus the flagged count)"
        )
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
