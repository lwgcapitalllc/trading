#!/usr/bin/env python3
"""miss_audit.py — the setups that got all the way and never traded, and what each one would cost to capture.

Aaron's question (2026-08-08): *"what about three-out-of-three trades? how much of these am I
actually missing out on, and what could I add to capture them?"*

A MISSED setup is not a blocked one. A block is a setup a toggle refused; a miss is a setup that
got to 2 or 3 of the three confluences and then DIED. The three, from `execution.py`:

    ARM    a liquidity sweep or an RSI divergence armed stage 1, from a source you have ENABLED
    SOS    always met — it is why the watch is open at all
    ZONE   price tagged the 0.5-0.886 band AND a gap was live in that band while it was there

So **3-of-3 means every confluence was there and the entry still never happened**, and the miss
code names the entry-side reason instead: 4 veto, 5 final hour, 6 HTF filter, 7 the limit rested
and price never came back to touch it. **2-of-3 means the ARM or the ZONE was missing** (codes
1/2/3) — a different problem, and mostly the ordinary way a setup dies.

**Each code maps to a lever, which is the point of the breakdown**, because "how do I capture
these" has a different answer per code:

    code 4  veto          -> exec_respect_veto = False
    code 5  final hour    -> exec_no_late_day  = False
    code 6  HTF filter    -> exec_htf_* (already 'Ignore' at the shipped defaults)
    code 7  never filled  -> a SHALLOWER entry model (exec_deep_fib / exec_fib_*)

⚠ **A count is not an opportunity, and this tool deliberately does NOT price one.** It reports how
many and where; what capturing them is WORTH must come from a real replay with the matching lever
flipped (`exit_audit.py --set ...`), for two reasons this repo has measured rather than argued:

  1. **One position slot.** An extra setup does not ADD to the book, it QUEUES in front of it —
     Run 12 replayed four separate ways of loosening this entry and every one displaced real
     trades, one of them a +16.5R winner. **Deleting or adding rows to a finished trade list gets
     the SIGN wrong**, which is exactly how the minimum-stop guard's cheap estimate said +1.84R
     where a replay said −1.84R.
  2. **A shallower entry is a WIDER stop.** The stop is pinned at the 0.886 fib whatever the
     entry, so entering at 0.618 instead of 0.786 does not merely add a fill — it moves the whole
     trade's R geometry, putting every target closer in R terms. The `exec_sec_retrace` sweep
     measured this shape directly: shallower entries were monotonically WORSE, +2 trades for −11R.

⚠ **Misses are recorded on every bar, warm-up included** (`execution.step` runs throughout; only
`decisions` is gated), so records before `--warmup` are dropped here. Counting them would credit
the window with setups that belong to the bars before it.

Usage:
    python backtest/tools/miss_audit.py --start 2020-01-01 --end 2026-08-06
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_STRATEGIES = {
    "sos_fade": "strategies.python.sos_fade",
    "b_leg": "strategies.python.b_leg",
}

# What would have to change for a miss of this code to become a trade. Reporting only — nothing
# here is applied; it is the shortlist a reader takes to `exit_audit.py --set`.
_LEVER = {
    1: "enable that arm source (exec_arm_sweep / exec_arm_div)",
    2: "nothing — price never came back. Not capturable by any setting.",
    3: "exec_req_fvg=False  (drop the gap requirement)",
    4: "exec_respect_veto=False",
    5: "exec_no_late_day=False",
    6: "exec_htf_exhaust_only / exec_htf_weekly / exec_htf_daily",
    7: "a SHALLOWER entry (exec_deep_fib=True, or exec_fib_nearest=False)",
}


def _pct(n: int, total: int) -> str:
    return f"{(100.0 * n / total):.1f}%" if total else "-"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Setups that never traded, and the lever for each.")
    ap.add_argument("--strategy", default="sos_fade", choices=sorted(_STRATEGIES))
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--set", dest="overrides", action="append", default=[], metavar="FIELD=VALUE")
    args = ap.parse_args(argv)

    import datetime as dt
    import importlib

    from backtest.data.source import BarSource

    mod = importlib.import_module(_STRATEGIES[args.strategy])
    spec = mod.LAB_STRATEGY
    StrategyCls, ConfigCls = spec["strategy"], spec["config"]

    end = args.end or dt.date.today().isoformat()
    print(f"loading {args.symbol} {args.tf}m  {args.start} -> {end} ...", flush=True)
    df = BarSource().load(args.symbol, args.tf, args.start, end)
    if df.empty:
        print("no bars — is the MT5 agent tunnel up on localhost:8766?")
        return 1
    print(f"  {len(df):,} bars  {df.index[0]} -> {df.index[-1]}", flush=True)

    cfg = ConfigCls(fill_model="bar", symbol=args.symbol)
    patch: dict = {}
    if hasattr(cfg, "exec_secondary"):
        patch["exec_secondary"] = False  # single-stream replay; see exit_audit.py
    for ov in args.overrides:
        field, raw = ov.split("=", 1)
        field = field.strip()
        if not hasattr(cfg, field):
            raise SystemExit(f"--set {field!r}: no such field on {ConfigCls.__name__}")
        cur = getattr(cfg, field)
        if isinstance(cur, bool):
            val = raw.strip().lower() in ("1", "true", "yes", "on")
        elif isinstance(cur, int) and not isinstance(cur, bool):
            val = int(float(raw))
        elif isinstance(cur, float):
            val = float(raw)
        else:
            val = raw
        patch[field] = val
        print(f"  override {field} = {val!r} (was {cur!r})")
    cfg = dataclasses.replace(cfg, **patch)

    print(f"replaying {args.strategy} (warmup {args.warmup}) ...", flush=True)
    strat = StrategyCls(config=cfg, initial_capital=args.capital)
    strat.run(df, warmup=args.warmup)

    trades = strat.execution.trades
    # Warm-up records belong to the bars before this window — see the module docstring.
    misses = [m for m in strat.execution.misses if m.index >= args.warmup]
    blocks = [b for b in strat.execution.blocks if b.index >= args.warmup]

    print("\n" + "=" * 92)
    print(
        f"{args.strategy}  {args.symbol} {args.tf}m   {df.index[0].date()} -> {df.index[-1].date()}"
    )
    print(f"  {len(trades)} trades   {len(misses)} missed setups   {len(blocks)} blocked setups")
    print("=" * 92)

    three = [m for m in misses if m.met >= 3]
    two = [m for m in misses if m.met == 2]
    print("\nMISSES BY HOW FAR THEY GOT")
    print(
        f"  3 of 3 — every confluence met, no trade   {len(three):>5}  {_pct(len(three), len(misses))}"
    )
    print(
        f"  2 of 3 — arm or zone missing              {len(two):>5}  {_pct(len(two), len(misses))}"
    )

    for label, grp in (("3 OF 3", three), ("2 OF 3", two)):
        if not grp:
            continue
        print(f"\n{label} — WHY IT NEVER TRADED")
        counts = Counter(m.code for m in grp)
        for code, n in counts.most_common():
            lbl = grp[0].labels[0] if False else None
            name = next((m.labels[0] for m in grp if m.code == code), f"code {code}")
            print(
                f"  {code}  {name:<24} {n:>5}  {_pct(n, len(grp)):>6}   -> {_LEVER.get(code, '?')}"
            )

    if three:
        print("\n3 OF 3 — SHAPE")
        by_dir = Counter("long" if m.dir > 0 else "short" for m in three)
        print("  direction: " + "  ".join(f"{d} {n}" for d, n in sorted(by_dir.items())))
        per_year: dict = defaultdict(lambda: [0, 0])
        for m in three:
            per_year[dt.datetime.utcfromtimestamp(m.time_ms / 1000).year][0] += 1
        for t in trades:
            per_year[dt.datetime.utcfromtimestamp(t.entry_ms / 1000).year][1] += 1
        print(f"  {'year':<8}{'3of3 missed':>13}{'traded':>9}")
        for y in sorted(per_year):
            miss_n, trade_n = per_year[y]
            print(f"  {y:<8}{miss_n:>13}{trade_n:>9}")

    print("\n⚠ A COUNT IS NOT AN OPPORTUNITY. Price each lever with a real replay:")
    print("    python backtest/tools/exit_audit.py --start ... --set <lever>")
    print("  One position slot means an added setup QUEUES in front of a real trade rather than")
    print("  adding to it, and a shallower entry widens the stop. Both have had their SIGN wrong")
    print("  when estimated from a finished trade list.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
