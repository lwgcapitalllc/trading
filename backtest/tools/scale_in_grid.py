#!/usr/bin/env python3
"""scale_in_grid.py — re-measure the SOS Fade scale-in budget after the 2026-09-22 sizing fix.

Run 21 (`strategies/python/sos_fade/sos_fade_optimization.md`) chose the shipped budget —
3 adds at a 0.5x cap — on an affordability rule that was later found to be **exact for one add
and double-spent from the second onward**: every add pledged the BASE lot's locked profit again
and never looked at the lots already bought. So the cell Run 21 picked was picked under a rule
that no longer exists, and the pick has to be re-earned rather than assumed.

This tool replays three ARMS over the same bars, same costs, same everything else, so the only
thing that moves between them is the rule:

    old        the pre-fix sizing (base lot only) on the pre-fix re-arm test
    fixed      the whole position's locked profit, pre-fix re-arm test
    fixed+gate the whole position's locked profit, and the stop must also have ratcheted past
               the price the last add was bought at

🔴 **THE `old` ARM IS PRODUCED BY PATCHING ONE EMULATOR INSTANCE, NOT BY CHECKING OUT THE OLD
FILE**, and that is deliberate. Two sessions share this clone, so a `git checkout` of a strategy
file mid-run would yank the tree out from under whoever else is in it. The patch shadows exactly
one method with the line it used to hold, on the one run that asked for it — never on the class,
because the first version of this tool did that and the pool carried it into the cells that were
supposed to be the control. Every cell asserts which of the two rules it actually ran, and the
line being replaced is checked against the shipped source before anything starts — see
`_OLD_LOCKED_SOURCE`.

⚠ **ITS NUMBERS DO NOT RECONCILE WITH RUN 21'S TABLE AND ARE NOT MEANT TO.** Run 21 ran on
2026-08-18; the exit ladder, the adds' own target and the trail have all moved since, and the
baseline here books 119.43R where Run 21's booked 128.26R. What this tool produces is an
internally MATCHED set — every cell in one invocation sees one config apart from the two levers
named in its row — which is the only comparison the question needs. Quoting a cell from here
against a number from Run 21 is rule 11, and it is the mistake this paragraph exists to stop.

Usage:
    python backtest/tools/scale_in_grid.py                    # the full grid
    python backtest/tools/scale_in_grid.py --adds 3 --caps 0.5   # one cell, all three arms
    python backtest/tools/scale_in_grid.py --workers 1        # serial, for a traceback
"""

from __future__ import annotations

import argparse
import dataclasses
import multiprocessing
import sys
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# The run's basis, in one place. Everything below reads it; nothing below hardcodes a second
# copy. Rule 11 — anything that recreates a run for comparison carries forward everything that
# decides what it is measured on, and a basis spread over five call sites drifts between arms.
SYMBOL = "XAUUSD.p"
SERVER = "PUPrime_Demo"
TIMEFRAME = "15"
START = "2018-09-14"  # the PU Prime cache's measured floor for this symbol and frame
END = "2026-08-14"
WARMUP = 1000
CAPITAL = 10_000.0
COST_PROFILE = "puprime_ecn"

#: The line the pre-fix affordability rule used, kept here so the `old` arm is readable rather
#: than implied. It is the BASE lot alone — no term for the lots already bought.
_OLD_LOCKED_SOURCE = "(stop - self._entry) * d * self._base_qty * pv"


def _old_locked_at_stop(self, stop: float) -> float:
    """The pre-fix reading: the profit the stop guarantees on the BASE lot only."""
    d, pv = self._pos_dir, self._pv()
    return (stop - self._entry) * d * self._base_qty * pv


def _metrics(trades) -> dict:
    """Total R, max drawdown in R off the cumulative curve, and the worst single trade.

    Drawdown is measured in R, never dollars — this strategy risks a % of equity, so a dollar
    drawdown late in a compounding run is not comparable with an early one (rule 6).
    """
    rs = [float(t.r) for t in trades]
    total = sum(rs)
    peak, dd = 0.0, 0.0
    run = 0.0
    for r in rs:
        run += r
        peak = max(peak, run)
        dd = max(dd, peak - run)
    return {
        "n": len(rs),
        "r": total,
        "dd": dd,
        "rdd": (total / dd) if dd > 0 else float("nan"),
        "worst": min(rs) if rs else 0.0,
    }


def _year(trade, index):
    """The calendar year a trade ENTERED, off its own UTC stamp.

    Never off `entry_index`: a re-entry counts bars on the fast feed, and reading that number
    against the 15m frame stamped 60 of 242 trades with the last bar of the run once already.
    """
    import pandas as pd

    ms = getattr(trade, "entry_ms", 0)
    if ms:
        return pd.Timestamp(ms, unit="ms").year
    i = min(max(int(trade.entry_index), 0), len(index) - 1)
    return index[i].year


def _run_cell(cell: dict) -> dict:
    """One replay. Runs in its own process, so it loads its own bars and imports its own
    strategy — nothing is shared, and the monkeypatch cannot leak into another arm."""
    from backtest.data.source import BarSource
    from backtest.fills import PROFILES
    from backtest.replay.build import build_strategy
    from backtest.replay.registry import load as load_strategy

    spec = load_strategy("sos_fade")
    StrategyCls, ConfigCls = spec["strategy"], spec["config"]

    cfg = ConfigCls(symbol=SYMBOL, fill_model="bar")
    cfg = dataclasses.replace(cfg, exec_secondary=False, **cell["overrides"])

    df = BarSource(server=SERVER).load(SYMBOL, TIMEFRAME, START, END)
    strat = build_strategy(
        StrategyCls, cfg, initial_capital=CAPITAL, cost_profile=PROFILES[COST_PROFILE]
    )

    # 🔴 THE OLD RULE IS BOUND TO THIS ONE EMULATOR, NEVER ASSIGNED TO THE CLASS. The first
    # version of this tool patched `Execution._locked_at_stop` on the class inside a worker, and
    # the pool REUSED that worker — so every cell that landed after an `old` cell silently ran
    # the old rule too. The table came back with the `old` and `fixed` columns identical to the
    # cent in all twelve rows, which reads exactly like *the fix changes nothing* rather than
    # like a bug, and it would have been written up that way. An instance attribute shadows the
    # method for this run alone, so no worker, pool size or serial mode can carry it anywhere.
    if cell["arm"] == "old":
        strat.execution._locked_at_stop = types.MethodType(_old_locked_at_stop, strat.execution)
    # Both directions, every cell: an arm that cannot say which rule it ran is not evidence.
    bound = strat.execution._locked_at_stop
    is_old = getattr(bound, "__func__", bound) is _old_locked_at_stop
    assert is_old == (cell["arm"] == "old"), (
        f"arm {cell['arm']!r} ran the {'old' if is_old else 'shipped'} sizing rule"
    )

    strat.run(df, warmup=WARMUP)
    trades = list(strat.execution.trades)

    out = dict(cell)
    out["all"] = _metrics(trades)
    out["ex20"] = _metrics([t for t in trades if _year(t, df.index) != 2020])
    out["adds_filled"] = sum(1 for t in trades if getattr(t, "adds", None))
    return out


def _cells(adds_list, caps_list, arms) -> list[dict]:
    cells = [
        {
            "arm": "off",
            "label": "no scaling",
            "overrides": {"exec_scale_in": False},
        }
    ]
    gate_for = {
        "old": "Stop improved",
        "fixed": "Stop improved",
        "fixed+gate": "Past the last add",
    }
    for arm in arms:
        for adds in adds_list:
            for cap in caps_list:
                cells.append(
                    {
                        "arm": arm,
                        "label": f"{arm:<10} {adds} x {cap}x",
                        "overrides": {
                            "exec_scale_in": True,
                            "exec_scale_mode": "Trail",
                            "exec_scale_max_adds": adds,
                            "exec_scale_cap_x": cap,
                            "exec_scale_gate": gate_for[arm],
                        },
                    }
                )
    return cells


def _print_table(results: list[dict]) -> None:
    head = (
        f"{'':<22}{'ALL R':>8}{'dd':>7}{'r/dd':>7}"
        f"{'EX20 R':>9}{'dd':>7}{'r/dd':>7}{'worst':>8}{'trades':>8}"
    )
    print()
    print(head)
    print("-" * len(head))
    base = next((r for r in results if r["arm"] == "off"), None)
    for r in results:
        a, e = r["all"], r["ex20"]
        gain = "" if base is None or r is base else f"  {a['r'] - base['all']['r']:+7.2f}"
        print(
            f"{r['label']:<22}{a['r']:>8.2f}{a['dd']:>7.2f}{a['rdd']:>7.2f}"
            f"{e['r']:>9.2f}{e['dd']:>7.2f}{e['rdd']:>7.2f}{a['worst']:>8.2f}{a['n']:>8}{gain}"
        )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--adds", type=int, nargs="+", default=[1, 2, 3, 4])
    ap.add_argument("--caps", type=float, nargs="+", default=[0.5, 1.0, 2.0])
    ap.add_argument(
        "--arms",
        nargs="+",
        default=["old", "fixed", "fixed+gate"],
        choices=["old", "fixed", "fixed+gate"],
    )
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args(argv)

    # Rule 12's shape applied to a measurement tool: the `old` arm is only worth reading if it
    # really is the old rule, so check the line it replaces is still the one in the file. A
    # later edit to the shipped method would otherwise leave this comparing the fix with itself.
    src = (_ROOT / "strategies/python/sos_fade/execution.py").read_text()
    if _OLD_LOCKED_SOURCE not in src:
        print(
            "the pre-fix line is no longer in execution.py, so the 'old' arm cannot be built "
            f"by patching it.\n  looked for: {_OLD_LOCKED_SOURCE}",
            file=sys.stderr,
        )
        return 1

    cells = _cells(args.adds, args.caps, args.arms)
    print(
        f"{len(cells)} cells  {SYMBOL} {TIMEFRAME}m  {START} -> {END}  "
        f"costs {COST_PROFILE}  warmup {WARMUP}  secondary off",
        flush=True,
    )

    if args.workers <= 1:
        results = [_run_cell(c) for c in cells]
    else:
        # `maxtasksperchild=1` is belt to the instance-level patch's braces — the arms are
        # already isolated per run, and a worker that dies after one cell also cannot carry a
        # warm engine cache between two cells that are meant to be independent.
        with multiprocessing.Pool(processes=args.workers, maxtasksperchild=1) as pool:
            results = pool.map(_run_cell, cells, chunksize=1)

    _print_table(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
