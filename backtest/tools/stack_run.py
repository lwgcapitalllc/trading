#!/usr/bin/env python3
"""stack_run.py — run several bots on ONE shared account, the way a demo account works.

Every backtest in this repo so far has replayed one bot against its own private balance. A
"stack" in the lab is still that: N standalone runs added together, which assumes each leg
traded a full account and was never refused. It is an UPPER BOUND, not a demo result.

This runs them together:

  * **one balance** — every leg sizes off the shared account, and every leg's P&L books onto
    it, so a loss on one shrinks the next trade of the other;
  * **one risk budget** — an open trade reserves risk to its CURRENT stop (a stop moved to
    breakeven frees its room), the cap is a % of the live balance, and an entry with no room
    is shrunk to fit or refused outright;
  * **one clock** — the legs are merged by timestamp, so the budget is right at the instant
    any leg asks.

It also replays each leg SOLO on the same bars and prints both. That control is the point: a
difference in the shared book is otherwise a mixture of *the cap bit* and *the shared balance
re-sized everything*, and nothing afterwards separates them.

⚠ **Read the CONTENTION table, not only the totals.** Zero contention means the cap never
bound, so the shared run and the solo runs differ only through the shared balance — which is
a real result (it says the legs do not fight) and NOT evidence the cap works. Tighten
`--risk-cap` until it bites before concluding anything about the gate.

⚠ **This is the BACKTEST side of the account rule. The live side is unbuilt** — live bots are
separate OS processes and cannot share this in-memory account (`docs/LIVE_TRADING_PIPELINE.md`
→ G10). Whatever rule is tuned here has to be the rule the live allocator enforces, or the
stacked backtest stops predicting the stacked account.

Usage:
    python backtest/tools/stack_run.py
    python backtest/tools/stack_run.py --legs sos_fade,b_leg --risk-cap 10
    python backtest/tools/stack_run.py --start 2020-01-01 --balance 10000 --risk-cap 12
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.portfolio import LegSpec, contention_summary, run_stack  # noqa: E402

# Same registry shape as run_report.py and overlap_audit.py — a package that declares
# LAB_STRATEGY is runnable here for free. Keep the three in step when a strategy lands.
_STRATEGIES = {
    "sos_fade": "strategies.python.sos_fade",
    "b_leg": "strategies.python.b_leg",
    "bos": "strategies.python.bos",
    "extreme_leg": "strategies.python.extreme_leg",
}


def _spec(key: str, df, symbol: str, risk_pct: float | None = None) -> LegSpec:
    mod = importlib.import_module(_STRATEGIES[key])
    lab = mod.LAB_STRATEGY
    ConfigCls = lab["config"]
    # ⚠ Only the fields this strategy DECLARES. `LAB_STRATEGY` is an OPEN CONTRACT — a config
    # may predate a kwarg, and `extreme_leg` has no `fill_model` at all (its fills are bar
    # fills with no switch). Passing every field unconditionally is a TypeError three lines into
    # the run; passing them conditionally by name is what `overlap_audit.py` already does, and
    # keeping the two tools the same shape is the point of the note on `_STRATEGIES`.
    wanted = {"fill_model": "bar", "symbol": symbol}
    have = getattr(ConfigCls, "__dataclass_fields__", {})
    cfg = ConfigCls(**{k: v for k, v in wanted.items() if k in have})
    # 🔴 PER-TRADE RISK IS A BASIS FIELD AND IT WAS INVISIBLE HERE UNTIL 2026-09-02.
    # Each leg was built at its OWN config default and the number was printed nowhere, so the
    # first mixed stack silently ran `sos_fade` at 10% against `extreme_leg` at 1% — a
    # 10:1 asymmetry nobody chose. The bigger leg then fills the shared budget on its own and
    # the smaller one reads as harmless, which is a fact about the SETTINGS rather than about
    # the strategies. It is printed in the leg table now, and `--risk-pct` matches them when
    # what you want is the two competing rather than one dwarfing the other.
    if risk_pct is not None and "exec_risk_pct" in have:
        import dataclasses

        cfg = dataclasses.replace(cfg, exec_risk_pct=risk_pct)
    # The 1m re-entry needs a second bar stream, which a leg does not have. `build_leg`
    # refuses it rather than replaying primary-only, so state the pin here where a reader
    # can see it instead of letting the run die three lines into the replay.
    if hasattr(cfg, "exec_secondary") and cfg.exec_secondary:
        import dataclasses

        cfg = dataclasses.replace(cfg, exec_secondary=False)
        print(f"  {key}: exec_secondary pinned OFF (a leg is one bar frame)")
    return LegSpec(name=key, strategy_cls=lab["strategy"], config=cfg, df=df)


def _book(trades) -> tuple[int, float]:
    return len(trades), round(sum(t.r for t in trades), 2)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--legs",
        default="sos_fade,b_leg",
        help=f"comma-separated, from {sorted(_STRATEGIES)}",
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument(
        "--tf",
        default="15",
        help="the frame a leg runs on unless it names its own as `leg:tf` in --legs",
    )
    ap.add_argument(
        "--server",
        default=None,
        help="the broker whose cached bars to read, e.g. PUPrime-Demo. Without it the bar "
        "source asks whichever MT5 terminal is attached, which needs the SSH tunnel up — so "
        "a re-run with the app down fails at the fetch rather than reading the cache it "
        "already holds. Two brokers' gold histories differ in LENGTH, so a stack re-run on "
        "the wrong cache disagrees with every figure while looking perfectly healthy. Name "
        "the server this stack was measured on.",
    )
    ap.add_argument(
        "--start",
        default=None,
        help="YYYY-MM-DD (default: the broker's measured earliest bar at this tf)",
    )
    ap.add_argument("--end", default=None)
    ap.add_argument(
        "--balance",
        type=float,
        default=10_000.0,
        help="the account's OPENING balance, shared by every leg",
    )
    ap.add_argument(
        "--risk-cap",
        type=float,
        default=10.0,
        help="max open risk as a %% of the LIVE balance, across all legs",
    )
    ap.add_argument(
        "--risk-pct",
        type=float,
        default=None,
        help="force EVERY leg to this per-trade risk %%, so the legs compete on one basis. "
        "Default: each leg keeps its own config default, which may differ between legs by a "
        "lot — the table prints what was used.",
    )
    ap.add_argument(
        "--entry-floor",
        type=float,
        default=0.0,
        help="skip an entry granted less than this %% of balance in risk",
    )
    args = ap.parse_args(argv)

    keys, tf_of = [], {}
    for token in (t.strip() for t in args.legs.split(",")):
        if not token:
            continue
        name, _, tf = token.partition(":")
        name = name.strip()
        keys.append(name)
        tf_of[name] = tf.strip() or args.tf
    unknown = [k for k in keys if k not in _STRATEGIES]
    if unknown:
        raise SystemExit(f"unknown strategies: {unknown}. Known: {sorted(_STRATEGIES)}")
    if len(keys) < 2:
        raise SystemExit(
            "a stack needs at least two legs — one leg on a shared account is "
            "just a solo run with extra steps."
        )

    from backtest.data.history import floor_for
    from backtest.data.source import BarSource

    frames = sorted({tf_of[k] for k in keys}, key=lambda t: int(t))

    # 🔴 THE START MUST BE THE LATEST FLOOR ACROSS THE FRAMES, NEVER EACH FRAME'S OWN.
    # The legs share one balance. Giving a 15m leg a year the 5m leg does not have lets it
    # compound alone before the other exists, and every later trade of BOTH legs is then sized
    # off a balance one of them built unopposed. The run would not be wrong so much as it would
    # be answering a different question, and nothing in the output says which.
    start = args.start
    if start is None:
        floors = {}
        for tf in frames:
            fl = floor_for(args.symbol, tf)
            if fl is None:
                raise SystemExit(
                    f"cannot measure the broker's earliest {tf}m history for {args.symbol}. "
                    f"Pass --start explicitly rather than guessing one."
                )
            floors[tf] = fl
        start = max(floors.values()).isoformat()
        if len(set(floors.values())) > 1:
            binding = max(floors, key=lambda t: floors[t])
            print(
                "  common window: "
                + ", ".join(f"{tf}m from {floors[tf]}" for tf in frames)
                + f" — starting at {start}, set by the {binding}m frame, so both legs "
                f"see the same history."
            )
    end = args.end or dt.date.today().isoformat()

    src = BarSource(server=args.server)
    dfs = {}
    for tf in frames:
        print(f"loading {args.symbol} {tf}m  {start} -> {end} ...", flush=True)
        d = src.load(args.symbol, tf, start, end)
        if d.empty:
            print(f"no {tf}m bars returned")
            return 1
        print(f"  {len(d):,} bars  {d.index[0]} -> {d.index[-1]}", flush=True)
        dfs[tf] = d

    specs = [_spec(k, dfs[tf_of[k]], args.symbol, args.risk_pct) for k in keys]
    print(f"replaying {len(specs)} legs shared + {len(specs)} solo controls ...", flush=True)
    run = run_stack(
        specs,
        balance=args.balance,
        risk_cap_pct=args.risk_cap / 100.0,
        entry_floor_pct=args.entry_floor / 100.0,
    )

    print()
    print(
        f"SHARED ACCOUNT   opening ${run.opening_balance:,.2f}   "
        f"cap {args.risk_cap:.2f}% of live balance"
    )
    print(f"                 closing ${run.closing_balance:,.2f}")
    print()
    # The frame is printed PER LEG because a mixed-frame stack is otherwise indistinguishable
    # from a single-frame one in this table, and the two are different runs.
    print(
        f"{'leg':<18}{'tf':>4}{'risk%':>7}{'shared trades':>15}{'shared R':>11}"
        f"{'solo trades':>14}{'solo R':>10}{'solo close':>14}"
    )
    for spec in specs:
        sn, sr = _book(run.per_leg.get(spec.name, []))
        on, orr = _book(run.solo_per_leg.get(spec.name, []))
        close = run.solo_closing.get(spec.name, 0.0)
        tf = f"{tf_of[spec.name]}m"
        rp = getattr(spec.config, "exec_risk_pct", None)
        rps = f"{rp:.2f}" if rp is not None else "?"
        print(
            f"{spec.name:<18}{tf:>4}{rps:>7}{sn:>15}{sr:>11.2f}{on:>14}{orr:>10.2f}{close:>14,.2f}"
        )
    tn, tr = _book(run.trades)
    print(f"{'TOTAL':<18}{'':>4}{'':>7}{tn:>15}{tr:>11.2f}")

    print()
    print(
        f"CARRIED     peak open risk {run.peak_reserved_pct * 100:.2f}% of the live balance "
        f"against a {args.risk_cap:.2f}% cap"
    )
    print(f"            peak legs holding at once: {run.peak_concurrent} of {len(specs)}")
    print("            (open risk is measured to each trade's CURRENT stop, so a stop moved to")
    print("             breakeven releases its room — which is why this can sit far under the cap")
    print("             on a book that was in the market the whole time.)")

    print()
    summary = contention_summary(run)
    if not summary:
        print("CONTENTION  none — the cap never bound, so the legs never actually competed.")
        print("            The shared and solo books differ only through the shared balance.")
        print(f"            Lower --risk-cap below {args.risk_cap:.2f} to make the gate bite.")
    else:
        print(f"CONTENTION  {len(run.contention)} events")
        print(f"{'leg':<16}{'shrunk':>9}{'blocked':>10}{'risk refused $':>18}")
        for leg, row in sorted(summary.items()):
            print(f"{leg:<16}{row['shrunk']:>9}{row['blocked']:>10}{row['risk_refused']:>18,.2f}")

    print()
    print(_invariant(run, specs))
    return 0


def _invariant(run, specs) -> str:
    """The one thing this tool can CHECK rather than report, and it is worth more than the totals.

    R is normalised to the trade's own risk, so scaling a position does not move it. With no
    contention the shared account grants every leg its full desired size, so the shared run and
    the solo run take the SAME trades and post the SAME R — the shared balance changes the
    DOLLARS (one balance compounding both legs) and nothing else. So:

      * no contention and equal R  → the seam is wired and neutral, which is what makes any
        later difference attributable to the cap;
      * no contention and DIFFERENT R → the account is moving decisions it should not touch,
        which is a defect in the seam, not a portfolio effect;
      * contention and equal R → the cap logged refusals that changed nothing, which usually
        means it is refusing entries the leg re-took a bar later. Read the log.

    Reported rather than raised: this is a research tool and a surprising result is the thing
    worth looking at, not a reason to exit non-zero on a long replay.
    """
    if run.contention:
        return (
            "⚠ The cap bound, so shared and solo are expected to differ. Every difference "
            "should\n  trace to a row in the contention log — check one before trusting the "
            "totals."
        )
    bad = []
    for spec in specs:
        shared_r = round(sum(t.r for t in run.per_leg.get(spec.name, [])), 6)
        solo_r = round(sum(t.r for t in run.solo_per_leg.get(spec.name, [])), 6)
        if shared_r != solo_r:
            bad.append(f"{spec.name}: shared {shared_r:+.2f}R vs solo {solo_r:+.2f}R")
    if not bad:
        return (
            "✅ No contention, and every leg posts the SAME R shared as solo — so the shared\n"
            "   account changed the dollars (one balance, compounding both legs) and moved "
            "no\n   decision. That is the control this run exists to establish."
        )
    return (
        "🔴 No contention, yet the R differs between shared and solo:\n   "
        + "\n   ".join(bad)
        + "\n   With nothing refused the two books should be identical in R — a difference\n"
        "   here is the shared account moving a decision it must not touch."
    )


if __name__ == "__main__":
    raise SystemExit(main())
