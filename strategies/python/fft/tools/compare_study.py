#!/usr/bin/env python3
"""compare_study.py — FFT's gate: the bot against the study, trade by trade, on the same bars.

FFT has no TradingView twin (the user cannot export 1-minute data), so this replaces the Pine
parity gate. Two independent implementations of the same rule run over the SAME PU Prime 1-minute
bars:

    the study   backtest/tools/fft_first_touch_study.py — an offline scan over whole arrays
    the bot     strategies/python/fft/ — minute by minute, orders decided at each close

It reports three things, strictest first:

  1. TRADES   every version-1 trade the study counts (first touch, all gates, first leg, no
              closure in the leg; stop 1.0, target TP2) is looked for in the bot at the same minute
              and side, and the outcome compared. Each study trade the bot did not take is named by
              the rule the bot says refused it.
  2. TOUCHES  every first touch the study found, looked for in the bot's touch list — the leg
              latching the two sides must agree on before any gate is even asked.
  3. COSTS    with --costs, the bot's trades through PU Prime ECN with bid/ask fills, against the
              ledger's +0.140R (2020-25) / +0.165R (last year).
  4. 15m BOS  the 15m trend's continuation BOS count at every first touch both sides found — what
              the overextension skip reads. With --overextended, the bot is run again with the skip
              ON and must take exactly its own trades minus those at 4+ (no trade overlaps another in
              version 1, so skipping one frees no slot for another).

EXIT 0 when the bot takes at least 95% of the study's trades AND takes no more than 5% extra, agrees
on at least 98% of the matched outcomes, and the two sides' first touches overlap by at least 95%
BOTH ways, and the 15m BOS count and the sweep label each agree on at least 98% of those touches
(the label was never compared before 2026-09-21, when both sides were found counting levels already
taken; and with
--overextended, the skip removes exactly the 4+ trades). ⚠ The extra-trade and bot-side-touch limits were added after the gate was MUTATED
(2026-09-21): with the bot's 15m rule forced to pass, it took 22 trades the study refuses, named
every one "study refused: 15m" — and still exited 0, because only MISSING trades were counted. ⚠ Green says the two AGREE; the
engines are shared, so an engine defect passes both — the user's chart check is what covers that.

⚠ **Both sides are fed the study's CLEANED bars** (reopen spikes clipped), so a difference here is
the rule layer's and never the data's. The study then walks outcomes on the RAW bars and the bot
on the cleaned ones, so an outcome can differ on a clipped reopen minute — named when it happens.

Usage:
  python strategies/python/fft/tools/compare_study.py                      # 2020-01 -> 2025-09
  python strategies/python/fft/tools/compare_study.py --start 2025-08-01 --end 2026-09-17
  python strategies/python/fft/tools/compare_study.py --costs
  python strategies/python/fft/tools/compare_study.py --overextended
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
for _p in (ROOT, ROOT / "strategies" / "python", ROOT / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

TRADE_MATCH = 0.95
OUTCOME_MATCH = 0.98
TOUCH_MATCH = 0.95
N15_MATCH = 0.98
SWEPT_MATCH = 0.98


def _ms(ts) -> int:
    return int(pd.Timestamp(ts).value // 10**6)


def study_side(start: str, end: str):
    import fft_first_touch_study as S

    touches, _, raw, _ = S.run(start, end)
    count_from = pd.Timestamp(start) + pd.Timedelta(days=S.WARMUP_DAYS)
    v1 = {}
    for t in touches:
        if t["kind"] != "first" or not S.gated(t, max_bos=0):
            continue
        r = t["res"].get(("61.8", "1.0", "TP2 38.2"))
        if r is None:
            continue
        v1[(_ms(t["t"]), t["d"])] = dict(win=r["win"], amb=r["amb"], lv=t["lv"], t=t)
    firsts = {(_ms(t["t"]), t["d"]): t for t in touches if t["kind"] == "first"}
    return v1, firsts, raw, count_from


def bot_side(raw: pd.DataFrame, profile=None, config=None):
    from loaded_level_study import clean_reopens

    import fft

    clean, _ = clean_reopens(raw)
    s = fft.FftStrategy(config=config, cost_profile=profile).run(clean)
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2025-09-01")
    ap.add_argument("--costs", action="store_true", help="also run the bot through PU Prime ECN")
    ap.add_argument("--show", type=int, default=15, help="list this many mismatches of each kind")
    ap.add_argument(
        "--overextended", action="store_true", help="also run the bot with the 15m 4+ BOS skip ON"
    )
    a = ap.parse_args()

    v1, firsts, raw, count_from = study_side(a.start, a.end)
    s = bot_side(raw)
    cf = _ms(count_from)
    ex = s.execution
    bot_trades = {(t.entry_ms, t.dir): t for t in ex.trades if t.entry_ms >= cf}
    bot_touch = {(t.ts_ms, t.dir): t for t in s.touches if t.kind == "first" and t.ts_ms >= cf}
    print(
        f"\nFFT bot vs study, {a.start} -> {a.end} (counting from {count_from.date()}), "
        f"bot ran {getattr(s, 'elapsed_s', 0):.0f}s"
    )

    # ── 1. trades ──
    matched = [k for k in v1 if k in bot_trades]
    missing = [k for k in v1 if k not in bot_trades]
    extra = [k for k in bot_trades if k not in v1]
    agree = sum(1 for k in matched if (bot_trades[k].exit_reason == "target") == v1[k]["win"])
    print("\n1. TRADES (version 1: first leg, all gates, stop 1.0, TP2)")
    print(
        f"   study {len(v1)}   bot {len(bot_trades)}   same minute and side {len(matched)} "
        f"({len(matched) / max(len(v1), 1):.1%})"
    )
    print(f"   outcome agrees on {agree} of {len(matched)}")
    why = Counter()
    for k in missing:
        bt = bot_touch.get(k)
        why[bt.why if bt is not None else "the bot recorded no first touch at this minute"] += 1
    if missing:
        print("   study trades the bot did not take, by the bot's reason:")
        for w, n in why.most_common():
            print(f"     {n:4d}  {w}")
    for k in missing[: a.show]:
        bt = bot_touch.get(k)
        print(
            f"     - {pd.Timestamp(k[0], unit='ms')} {'buy' if k[1] > 0 else 'sell'}: "
            f"{bt.why if bt else 'no touch'}"
        )
    if extra:
        print(f"   bot trades the study does not count: {len(extra)}")
        for k in extra[: a.show]:
            st = firsts.get(k)
            if st is None:
                note = "the study has no first touch at this minute"
            else:
                fails = [
                    n
                    for n, ok in (
                        ("15m", st["g15"]),
                        ("1m trend", st["g1dir"]),
                        ("1m break", st["g1clean"]),
                        ("closure", not st["weekend"]),
                        ("first leg", st["nbos"] <= 0),
                    )
                    if not ok
                ]
                note = "study refused: " + (", ".join(fails) or "outcome unresolved")
            print(f"     + {pd.Timestamp(k[0], unit='ms')} {'buy' if k[1] > 0 else 'sell'}: {note}")
    for k in [k for k in matched if (bot_trades[k].exit_reason == "target") != v1[k]["win"]][
        : a.show
    ]:
        print(
            f"     ≠ {pd.Timestamp(k[0], unit='ms')} study {'win' if v1[k]['win'] else 'loss'}"
            f"{' (same-minute ambiguity)' if v1[k]['amb'] else ''}, bot {bot_trades[k].exit_reason}"
        )

    # ── 2. touches ──
    sf = {k for k, t in firsts.items() if k[0] >= cf}
    both = sf & set(bot_touch)
    print("\n2. FIRST TOUCHES (the leg latch, before any gate)")
    print(
        f"   study {len(sf)}   bot {len(bot_touch)}   both {len(both)} ({len(both) / max(len(sf), 1):.1%})"
    )

    # ── 4. the 15m BOS count ──
    n15_ok = sum(1 for k in both if bot_touch[k].nbos15 == firsts[k]["n15"])
    print("\n4. 15m BOS COUNT at the first touches both found (what the overextension skip reads)")
    print(f"   agrees on {n15_ok} of {len(both)} ({n15_ok / max(len(both), 1):.1%})")
    for k in [k for k in both if bot_touch[k].nbos15 != firsts[k]["n15"]][: a.show]:
        print(
            f"     ≠ {pd.Timestamp(k[0], unit='ms')} study {firsts[k]['n15']}, "
            f"bot {bot_touch[k].nbos15}"
        )
    sw_ok = sum(1 for k in both if bool(bot_touch[k].swept) == bool(firsts[k]["swept"]))
    print(
        f"   the sweep label (A+) agrees on {sw_ok} of {len(both)} ({sw_ok / max(len(both), 1):.1%})"
    )
    for k in [k for k in both if bool(bot_touch[k].swept) != bool(firsts[k]["swept"])][: a.show]:
        print(
            f"     ≠ {pd.Timestamp(k[0], unit='ms')} study {firsts[k]['swept']}, "
            f"bot {bot_touch[k].swept}"
        )
    over_ok = True
    if a.overextended:
        import fft
        from fft.config import OVEREXTENDED_15M_BOS

        def nbos15_of(run, t) -> int:
            """The 15m count on the touch this trade filled from: the last traded touch before it
            on its side — one position at a time, so it can be no other."""
            got = [x for x in run.touches if x.traded and x.dir == t.dir and x.ts_ms <= t.entry_ms]
            return got[-1].nbos15 if got else -1

        off = {(t.entry_ms, t.dir) for t in ex.trades if t.entry_ms >= cf}
        flagged = {
            (t.entry_ms, t.dir)
            for t in ex.trades
            if t.entry_ms >= cf and nbos15_of(s, t) >= OVEREXTENDED_15M_BOS
        }
        so = bot_side(raw, config=fft.FftConfig(skip_15m_overextended=True))
        on = {(t.entry_ms, t.dir) for t in so.execution.trades if t.entry_ms >= cf}
        study_flag = sum(1 for k, v in v1.items() if v["t"]["n15"] >= OVEREXTENDED_15M_BOS)
        over_ok = on == off - flagged
        refused = sum(1 for x in so.touches if x.why == "bos15" and x.ts_ms >= cf)
        print("\n   with the skip ON:")
        print(
            f"   bot trades {len(on)} = {len(off)} - {len(flagged)} at 4+ BOS? "
            f"{'yes' if over_ok else 'NO'}   (study trades at 4+: {study_flag}; "
            f"touches refused 'bos15': {refused})"
        )
        for k in sorted((on ^ (off - flagged)))[: a.show]:
            print(
                f"     ≠ {pd.Timestamp(k[0], unit='ms')} {'only ON' if k in on else 'only expected'}"
            )

    # ── 3. costs ──
    if a.costs:
        from backtest.fills import PROFILES

        prof = dataclasses.replace(PROFILES["puprime_ecn"], bid_ask_fills=True)
        sc = bot_side(raw, prof)
        rs = [t.r for t in sc.execution.trades if t.entry_ms >= cf]
        wins = sum(1 for t in sc.execution.trades if t.entry_ms >= cf and t.exit_reason == "target")
        print("\n3. COSTS — PU Prime ECN, bid/ask fills, commission, swap")
        print(
            f"   {len(rs)} trades, win {wins / max(len(rs), 1):.1%}, avgR {np.mean(rs):+.3f}, "
            f"total {np.sum(rs):+.2f}R   (ledger: +0.140R 2020-25, +0.165R last year)"
        )

    extra_ok = len(extra) <= (1 - TRADE_MATCH) * len(v1)
    ok = (
        len(matched) >= TRADE_MATCH * len(v1)
        and extra_ok
        and agree >= OUTCOME_MATCH * max(len(matched), 1)
        and len(both) >= TOUCH_MATCH * len(sf)
        and len(both) >= TOUCH_MATCH * len(bot_touch)
        and n15_ok >= N15_MATCH * max(len(both), 1)
        and sw_ok >= SWEPT_MATCH * max(len(both), 1)
        and over_ok
    )
    print(
        f"\n{'MATCH OK' if ok else 'MISMATCH'} — trades {len(matched)}/{len(v1)} (need "
        f"{TRADE_MATCH:.0%}), extra bot trades {len(extra)} (allowed "
        f"{int((1 - TRADE_MATCH) * len(v1))}), outcomes {agree}/{len(matched)} (need "
        f"{OUTCOME_MATCH:.0%}), touches {len(both)} of study {len(sf)} / bot {len(bot_touch)} "
        f"(need {TOUCH_MATCH:.0%} of each), 15m BOS {n15_ok}/{len(both)} (need {N15_MATCH:.0%}), sweep label {sw_ok}/{len(both)} "
        f"(need {SWEPT_MATCH:.0%})"
        + ("" if not a.overextended else f", skip ON removes exactly the 4+ trades: {over_ok}")
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
