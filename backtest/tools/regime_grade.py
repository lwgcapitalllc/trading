#!/usr/bin/env python3
"""regime_grade.py — score the market-condition engine, so a change to it can be proved better.

Runs two graders and prints the result in plain English.

  1. Does a reading of the market predict what the market does next?  (tens of thousands of bars)
  2. Under each reading, did a bot make or lose money?                (a few hundred trades)

🔴 **READ THE RANGE, NEVER THE MIDDLE NUMBER.** Every figure printed here comes with the range it
could plausibly be. A range that crosses the no-effect point means the reading told us nothing,
and this tool says so in words rather than leaving a small number to be read as a small effect.

Usage:
    python backtest/tools/regime_grade.py
    python backtest/tools/regime_grade.py --tf 240 --horizon 30
    python backtest/tools/regime_grade.py --trades backtest/reports/<stamp>/trades.csv

The trade list is anything with an entry timestamp and an R column — `run_report.py` writes one.
Without it only grader 1 runs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.regime_study import forward, grade_bot, grade_market, measures  # noqa: E402


def _fmt(value, places: int = 3) -> str:
    return "—" if value is None else f"{value:.{places}f}"


def _verdict(lo, hi, no_effect: float = 0.0) -> str:
    """The sentence that stops a small number being read as a small effect."""
    if lo is None or hi is None:
        return "not enough data"
    if lo <= no_effect <= hi:
        return "TELLS US NOTHING"
    return "real, stronger side up" if lo > no_effect else "real, stronger side down"


def _print_market(scored: dict, walked: pd.DataFrame, horizon: int) -> None:
    print("\n" + "=" * 78)
    print(f"GRADER 1 — does a reading predict the next {horizon} bars?")
    print("=" * 78)
    print(f"{len(walked):,} bars graded\n")

    for outcome, ospec in forward.OUTCOMES.items():
        print(f"\n--- outcome: {ospec['label']} ---")
        print(f"{'reading':<26}{'n':>8}{'link':>8}{'range':>18}   verdict")
        for name, spec in measures.READINGS.items():
            cell = scored["readings"].get(name, {}).get(outcome)
            if not cell:
                continue
            rng = f"{_fmt(cell['lo'])} to {_fmt(cell['hi'])}"
            print(
                f"{name:<26}{cell['n']:>8,}{_fmt(cell['rho']):>8}{rng:>18}   "
                f"{_verdict(cell['lo'], cell['hi'])}"
            )

    share = grade_market.label_share(walked)
    flips = grade_market.flip_rate(walked)
    print("\n--- the shipped engine's labels ---")
    for name, frac in sorted(share.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<18} {100 * frac:5.1f}% of bars")
    if flips is not None:
        print(f"\n  the label changes on {100 * flips:.1f}% of bars")
        if flips > 0.10:
            print("  ⚠ that is too unstable to gate a bot on — it would switch inside one move")

    for outcome, cell in scored["label"].items():
        differ = cell["differ"]
        print(f"\n  under each label, {forward.OUTCOMES[outcome]['label']}:")
        for name, stat in sorted(cell["groups"].items()):
            rng = (
                f"  (could be {_fmt(stat['lo'])} to {_fmt(stat['hi'])})"
                if stat["lo"] is not None
                else "  (too few to put a range on)"
            )
            print(f"    {name:<18} n={stat['n']:>7,}  avg {_fmt(stat['mean'])}{rng}")
        if differ["share_as_extreme"] is not None:
            odds = differ["share_as_extreme"]
            note = (
                "the labels are telling us nothing here"
                if odds > 0.05
                else "the labels really do separate this"
            )
            print(f"    -> shuffling the labels beats this {100 * odds:.1f}% of the time: {note}")


def _print_bot(scored: dict, tagged: pd.DataFrame) -> None:
    print("\n" + "=" * 78)
    print("GRADER 2 — under each reading, did the bot make or lose money?")
    print("=" * 78)
    print(f"{scored['n_trades']} trades\n")

    print(f"{'reading':<26}{'n':>6}{'link to R':>11}{'range':>18}   verdict")
    for name in measures.READINGS:
        cell = scored["readings"].get(name)
        if not cell:
            continue
        rel = cell["relationship"]
        rng = f"{_fmt(rel['lo'])} to {_fmt(rel['hi'])}"
        print(
            f"{name:<26}{rel['n']:>6}{_fmt(rel['rho']):>11}{rng:>18}   "
            f"{_verdict(rel['lo'], rel['hi'])}"
        )

    for name in measures.READINGS:
        rows = scored["readings"].get(name, {}).get("bands") or []
        if not rows:
            continue
        print(f"\n  {name} — average R by band:")
        for row in rows:
            rng = (
                f"could be {_fmt(row['lo'], 2)} to {_fmt(row['hi'], 2)}"
                if row["lo"] is not None
                else "too few to put a range on"
            )
            print(
                f"    {_fmt(row['from'], 2):>8} to {_fmt(row['to'], 2):<8} "
                f"n={row['n']:>4}  avg {_fmt(row['mean'], 2):>6} R   ({rng})"
            )

    if scored.get("label", {}).get("groups"):
        print("\n  the shipped engine's labels — average R:")
        for name, stat in sorted(scored["label"]["groups"].items()):
            rng = (
                f"could be {_fmt(stat['lo'], 2)} to {_fmt(stat['hi'], 2)}"
                if stat["lo"] is not None
                else "too few to put a range on"
            )
            print(f"    {name:<18} n={stat['n']:>4}  avg {_fmt(stat['mean'], 2):>6} R   ({rng})")
        odds = scored["label"]["differ"]["share_as_extreme"]
        if odds is not None:
            note = (
                "this table is what shuffling produces — the labels are not separating the bot"
                if odds > 0.05
                else "the labels really do separate this bot's results"
            )
            print(f"    -> shuffling beats this {100 * odds:.1f}% of the time: {note}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument(
        "--tf",
        default="240",
        help="the frame the market CONDITION is judged on, in minutes. 240 (4-hourly) by "
        "default: a condition is a multi-day property, and judging it on a few hours of "
        "5-minute bars is what the shipped engine is asked to do today.",
    )
    ap.add_argument("--start", default="2018-07-25")
    ap.add_argument("--end", default=None)
    ap.add_argument(
        "--horizon",
        type=int,
        default=30,
        help="how many bars ahead the outcome is measured over (30 four-hourly bars = ~1 week)",
    )
    ap.add_argument("--step", type=int, default=1, help="grade every Nth bar")
    ap.add_argument(
        "--long-multiple",
        type=int,
        default=6,
        help="the shipped engine takes two frames; the slow one is this many times the fast one "
        "(6 x 4-hourly = daily). Recorded in the manifest because it changes every label.",
    )
    ap.add_argument("--trades", default=None, help="a trades.csv to run grader 2 on")
    ap.add_argument("--trade-time-col", default="entry_utc")
    ap.add_argument("--trade-r-col", default="r")
    ap.add_argument("--no-label", action="store_true", help="skip the shipped label (faster)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    from backtest.data.source import BarSource

    end = args.end or dt.date.today().isoformat()
    print(f"loading {args.symbol} {args.tf}m  {args.start} -> {end} ...", flush=True)
    df = BarSource().load(args.symbol, args.tf, args.start, end)
    if df.empty:
        print("no bars returned — is the MT5 agent tunnel up on localhost:8766?")
        return 1
    print(f"  {len(df):,} bars  {df.index[0]} -> {df.index[-1]}", flush=True)

    out = (
        Path(args.out)
        if args.out
        else _ROOT
        / "backtest"
        / "reports"
        / ("regime_grade_" + dt.datetime.now().strftime("%Y%m%dT%H%M%S"))
    )
    out.mkdir(parents=True, exist_ok=True)

    # Rule 11: everything that decides what this was measured on travels with the result, or the
    # next reader cannot tell why two reports disagree.
    manifest = {
        "symbol": args.symbol,
        "condition_tf_min": args.tf,
        "start": args.start,
        "end": end,
        "bars": int(len(df)),
        "first_bar": str(df.index[0]),
        "last_bar": str(df.index[-1]),
        "horizon_bars": args.horizon,
        "step": args.step,
        "long_multiple": args.long_multiple,
        "labels_graded": not args.no_label,
        "trades": args.trades,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
    }

    print(f"grading the market over {args.horizon}-bar horizons ...", flush=True)
    walked = grade_market.walk(
        df,
        horizon=args.horizon,
        step=args.step,
        long_multiple=args.long_multiple,
        with_label=not args.no_label,
    )
    market = grade_market.score(walked)
    walked.to_csv(out / "market_rows.csv", index=False)
    (out / "market_grade.json").write_text(json.dumps(market, indent=2, default=str))
    _print_market(market, walked, args.horizon)

    bot = None
    if args.trades:
        trades = pd.read_csv(args.trades)
        print(f"\ntagging {len(trades)} trades ...", flush=True)
        tagged = grade_bot.tag(
            trades,
            df,
            time_col=args.trade_time_col,
            r_col=args.trade_r_col,
            long_multiple=args.long_multiple,
            with_label=not args.no_label,
        )
        bot = grade_bot.score(tagged)
        tagged.to_csv(out / "trade_rows.csv", index=False)
        (out / "bot_grade.json").write_text(json.dumps(bot, indent=2, default=str))
        _print_bot(bot, tagged)

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nwritten to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
