#!/usr/bin/env python3
"""shadow_diff.py — did the LIVE bot decide what the LAB says it should have?

Step 9.2 of `docs/LIVE_TRADING_PIPELINE.md`, and the reason it exists: the live bot and the
lab replay run **the same strategy object**. `algos/live/` supplies bars and mirrors intent
onto the broker; it contains no trading logic. So over the same window the two decision
streams should be identical, and **any difference is a data problem — a feed, a clock, or a
warm-up — never a logic one.** That is a narrow, checkable claim, which is what makes this a
useful gate rather than a vague reassurance.

**What it compares.** `runner.py` writes one `bar` record per closed bar it processed
(`ledger.py`). This replays the same window through `backtest/replay` with the bot's own
promoted parameters, joins the two streams **on bar TIMESTAMP**, and diffs them field by field.

⚠ **Joined on TIME, never on bar index.** The live bot's index counts on from wherever its
warm-up stopped and survives restarts; the lab's counts from the first row of whatever frame
it was handed. The two are unrelated integers that look comparable, which is exactly the trap
`strategies/CLAUDE.md` records from the B-LEG harness — 2,409 comparisons failed at one flat
offset while the logic was bar-for-bar identical.

⚠ **FEED drift and DECISION drift are reported SEPARATELY, and that separation is the point.**
The live bot trades PU Prime `XAUUSD.s` on the MT5_FFT terminal; the lab replays Vantage
`XAUUSD` out of MT5_Lab, deliberately, because that is the feed every backtest here was
measured on. **They are different brokers, so their bars genuinely differ**, and a price
difference that reaches the strategy comes back out as a decision difference. Merging the two
would let a two-cent quote gap read as a strategy bug — or, far worse, let a real logic
divergence hide inside an expected price gap. Read the feed section first: it is the
denominator for everything under it.

⚠ **A missing lab bar is a FINDING, not a skip.** If the live bot processed a bar the lab feed
has no row for, the two brokers disagree about when a bar closed, and that is a clock problem —
which is the specific thing this step of the plan exists to catch before anything is armed.

⚠ **It compares only the `Decision` fields the ledger records.** `l_sos_bar` / `s_sos_bar` /
`l_arm_src` / `s_arm_src` come off the SEQUENCE object, which a replay does not retain per bar,
and they are reported as uncompared rather than quietly dropped. Do not read a green run as
"every field matched" — read it as "every field that can be compared matched".

Usage:
    python algos/tools/shadow_diff.py --ledger <dir-or-file> [--config live_config.json]
    python algos/tools/shadow_diff.py --ledger /tmp/led --lab-symbol XAUUSD --tf 15
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# The Decision fields the ledger records and this tool can therefore diff. Split by kind
# because a float needs a tolerance and a bool does not, and because a price mismatch of one
# cent and a flipped veto are not the same size of news.
_BOOL_FIELDS = ["long_armed", "short_armed", "long_veto", "short_veto"]
_INT_FIELDS = ["l_stage", "s_stage"]
_PRICE_FIELDS = ["long_edge", "short_edge", "stop", "tp1", "tp2"]

# Fields the ledger carries that come from the SEQUENCE, not the Decision. A replay does not
# keep the per-bar sequence object, so these cannot be diffed here. Named out loud so a clean
# report is not mistaken for a complete one.
_UNCOMPARED = ["l_sos_bar", "s_sos_bar", "l_arm_src", "s_arm_src"]

# Two prices closer than this are the same price. Gold quotes to 2dp on both brokers, so a
# tenth of a cent is comfortably inside "identical" and far below any real quote difference.
_PRICE_EPS = 0.001


def _load_ledger(target: Path) -> list[dict]:
    files = sorted(target.glob("decisions-*.jsonl")) if target.is_dir() else [target]
    if not files:
        raise SystemExit(f"no decisions-*.jsonl found in {target}")
    rows: list[dict] = []
    for f in files:
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("kind") == "bar" and r.get("bar_time"):
                rows.append(r)
    rows.sort(key=lambda r: r["bar_time"])
    return rows


def _replay(params: dict, df, warmup: int):
    """Replay the lab with the bot's OWN promoted parameters.

    Built through `backtest.replay.build_strategy` rather than by constructing the class —
    the repo rule from the frictionless-lab bug. Unknown keys are dropped with a warning
    instead of raising: an instance config can outlive a schema, and a stale key must not stop
    the comparison that would reveal it.
    """
    import dataclasses

    from backtest.replay import build_strategy
    from strategies.python.sos_fade import LAB_STRATEGY

    ConfigCls = LAB_STRATEGY["config"]
    known = {f.name for f in dataclasses.fields(ConfigCls)}
    unknown = sorted(set(params) - known)
    if unknown:
        print(
            f"  ! instance config carries {len(unknown)} field(s) this build does not know: "
            f"{', '.join(unknown)}"
        )
    cfg = ConfigCls(**{k: v for k, v in params.items() if k in known})

    strat = build_strategy(LAB_STRATEGY["strategy"], cfg, initial_capital=10_000.0)
    strat.run(df, warmup=warmup)
    return strat


def _same_price(a, b) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) < _PRICE_EPS


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--ledger", required=True, help="ledger dir or a single decisions-*.jsonl")
    ap.add_argument(
        "--config",
        default=None,
        help="the bot's instance config.json (for its promoted strategy_params)",
    )
    ap.add_argument(
        "--lab-symbol",
        default="XAUUSD",
        help="symbol in the LAB's cache (Vantage), not the live symbol",
    )
    ap.add_argument("--tf", default="15")
    ap.add_argument(
        "--warmup",
        type=int,
        default=5000,
        help="bars the lab warms on before the compared window; match the bot's",
    )
    ap.add_argument("--show", type=int, default=8, help="example mismatches to print per field")
    args = ap.parse_args(argv)

    import pandas as pd

    from backtest.data.source import BarSource

    live = _load_ledger(Path(args.ledger))
    if not live:
        raise SystemExit("the ledger holds no bar records — has the bot run?")

    first_ms, last_ms = live[0]["bar_time"], live[-1]["bar_time"]
    first = pd.Timestamp(first_ms, unit="ms")
    last = pd.Timestamp(last_ms, unit="ms")

    params: dict = {}
    live_symbol = "?"
    if args.config:
        cfg_json = json.loads(Path(args.config).read_text())
        params = dict(cfg_json.get("strategy_params") or {})
        live_symbol = params.get("symbol", "?")
        # The lab loads its own broker's symbol; carrying the live suffix through would ask the
        # cache for a symbol it has never held.
        params.pop("symbol", None)

    # Warm-up is measured in BARS, so it has to be converted to calendar days with room for
    # weekends and the daily close break — gold trades ~96 bars a weekday out of 96 possible,
    # so ~5 days a week. Overshooting costs a few seconds of load; undershooting silently
    # replays a colder engine than the bot had and reports its own cold start as drift.
    tf_min = int(args.tf)
    days_back = max(10, int(args.warmup * tf_min / 60 / 24 * 7 / 5) + 10)
    load_from = (first - pd.Timedelta(days=days_back)).date().isoformat()
    load_to = (last + pd.Timedelta(days=1)).date().isoformat()

    print(f"live ledger : {len(live)} bars  {first} -> {last}   (symbol {live_symbol})")
    print(f"loading lab : {args.lab_symbol} {args.tf}m  {load_from} -> {load_to} ...", flush=True)
    df = BarSource().load(args.lab_symbol, args.tf, load_from, load_to)
    if df.empty:
        raise SystemExit("no lab bars returned")

    # Everything at or after the first live bar is the compared window; everything before it is
    # warm-up. Deriving the split from the DATA rather than from --warmup means the engines see
    # every bar available, and the count reported below is the real one.
    pos = int(df.index.searchsorted(first))
    print(
        f"  {len(df):,} bars  {df.index[0]} -> {df.index[-1]}   "
        f"(warm-up {pos:,} bars before the window)",
        flush=True,
    )
    if pos < args.warmup:
        print(
            f"  ! only {pos:,} warm-up bars available, the bot had {args.warmup:,} — "
            f"engine state may differ and show up below as drift"
        )

    strat = _replay(params, df, warmup=0)
    lab = {int(df.index[d.index].timestamp() * 1000): d for d in strat.decisions}
    lab_close = {int(t.timestamp() * 1000): float(c) for t, c in zip(df.index, df["close"])}

    # ── join ──
    # A live bar AFTER the lab feed ends is a stale cache, not a disagreement about when a bar
    # closed. Reporting the two together would manufacture a clock finding out of a cache that
    # simply has not been refreshed — and this tool is only worth running if a finding here
    # means something. They are counted apart.
    lab_last_ms = int(df.index[-1].timestamp() * 1000)
    matched, no_bar, past_end = [], [], []
    for row in live:
        d = lab.get(row["bar_time"])
        if d is not None:
            matched.append((row, d))
        elif row["bar_time"] > lab_last_ms:
            past_end.append((row, None))
        else:
            no_bar.append((row, None))

    w = 92
    print("\n" + "=" * w)
    print("SHADOW DIFF — live decision stream vs a lab replay of the same window")
    print("=" * w)

    print(f"\nlive bars recorded      {len(live):5d}")
    print(f"matched a lab bar       {len(matched):5d}  ({100.0 * len(matched) / len(live):.1f}%)")
    print(f"past the lab feed's end {len(past_end):5d}", end="")
    if past_end:
        print(f"   <- the lab cache stops at {df.index[-1]};")
        print("                              refresh it to compare these (NOT a clock finding)")
    else:
        print("")
    print(f"NO lab bar at that time {len(no_bar):5d}", end="")
    if no_bar:
        print("   <- the two feeds disagree about when a bar closed (a CLOCK finding)")
        for row, _ in no_bar[: args.show]:
            print(f"    {pd.Timestamp(row['bar_time'], unit='ms')}  close {row['close']}")
        if len(no_bar) > args.show:
            print(f"    ... and {len(no_bar) - args.show} more")
    else:
        print("   <- every live bar has a lab bar at the same timestamp")

    if not matched:
        print("\nnothing to compare.")
        return 1

    # ── feed ──
    # SIGNED, deliberately. An absolute difference makes a systematic quote offset and random
    # noise print identically — "min 0.04 median 0.05" reads as jitter when it is in fact one
    # broker quoting consistently above the other, which is a completely different fact about
    # the feed and the only one of the two that cannot cause a trade to flip.
    diffs = [
        round(lab_close[row["bar_time"]] - row["close"], 4)
        for row, _ in matched
        if row["bar_time"] in lab_close
    ]
    same = sum(1 for d in diffs if abs(d) < _PRICE_EPS)
    print(f"\n--- FEED: the bar CLOSE, live ({live_symbol}) vs lab ({args.lab_symbol}) ---")
    print(f"  identical closes  {same} of {len(diffs)}")
    if diffs:
        signed = [d for d in diffs if abs(d) >= _PRICE_EPS]
        one_way = all(d > 0 for d in signed) or all(d < 0 for d in signed)
        print(
            f"  lab MINUS live    min ${min(diffs):+.3f}  median ${statistics.median(diffs):+.3f}"
            f"  max ${max(diffs):+.3f}"
        )
        print(
            f"  always one way?   {'YES' if one_way else 'NO'}"
            f"   <- {'a systematic quote offset, not drift' if one_way else 'the gap changes sign, so it is not a fixed offset'}"
        )
    print("  ⚠ These are DIFFERENT BROKERS by design — the live bot trades PU Prime and every")
    print("    backtest here was measured on Vantage. A non-zero difference is expected, and it")
    print("    is the denominator for the decision section below, not a defect on its own.")

    # ── decisions ──
    mismatch: dict[str, list] = defaultdict(list)
    for row, d in matched:
        for f in _BOOL_FIELDS:
            if bool(row.get(f)) != bool(getattr(d, f)):
                mismatch[f].append((row["bar_time"], row.get(f), getattr(d, f)))
        for f in _INT_FIELDS:
            if int(row.get(f) or 0) != int(getattr(d, f) or 0):
                mismatch[f].append((row["bar_time"], row.get(f), getattr(d, f)))
        for f in _PRICE_FIELDS:
            if not _same_price(row.get(f), getattr(d, f)):
                mismatch[f].append((row["bar_time"], row.get(f), getattr(d, f)))

    total = sum(len(v) for v in mismatch.values())
    print(
        f"\n--- DECISIONS: {len(matched)} bars x {len(_BOOL_FIELDS) + len(_INT_FIELDS) + len(_PRICE_FIELDS)} fields ---"
    )
    if not mismatch:
        print("  IDENTICAL on every compared field.")
    else:
        print(f"  {total} mismatches across {len(mismatch)} field(s):\n")
        for f in sorted(mismatch, key=lambda k: -len(mismatch[k])):
            rows = mismatch[f]
            print(f"  {f:<14} {len(rows):4d} / {len(matched)} bars")
            for ms, a, b in rows[: args.show]:
                print(f"      {pd.Timestamp(ms, unit='ms')}   live={a!r:<14} lab={b!r}")
            if len(rows) > args.show:
                print(f"      ... and {len(rows) - args.show} more")

    print(
        f"\n  not compared: {', '.join(_UNCOMPARED)}"
        f"  (sequence state, which a replay does not retain per bar)"
    )
    return 0 if not mismatch and not no_bar else 2


if __name__ == "__main__":
    raise SystemExit(main())
