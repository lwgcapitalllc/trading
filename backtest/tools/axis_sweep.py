#!/usr/bin/env python3
"""axis_sweep.py — move ONE setting at a time off a strategy's shipped defaults, and score
every value in R with its neighbours, its two calendar halves and a control beside it.

**Why one axis at a time rather than a grid.** A cartesian product over a book of ~100 trades
returns a winner whether or not one exists, and this repo has already paid for that twice
(`strategies/python/extreme_leg/extreme_leg_optimization.md` Runs 3 and 6, where a 509,000-cell
search and a 160-cell one both named winners that their own neighbours refuted). Sweeping an axis
means every row's NEIGHBOURS are in the table by construction, and a hill and a spike stop looking
alike. Combine the survivors afterwards, deliberately, and re-check both halves.

**The four rules it ENFORCES rather than reminds you of**, because each is a rule somebody here
has broken:

  1. `--split` is REQUIRED. The out-of-sample boundary is declared on the command line, before a
     row runs, and is echoed above the table. Deciding it after seeing the grid is how a sweep
     launders noise into a default.
  2. A CONTROL row at the shipped defaults is always run and always printed first. With
     `--expect-trades` / `--expect-r` it is ASSERTED and the tool refuses when it misses: if the
     control has moved, the harness moved, and no row underneath it is readable. Without them it
     prints a loud UNASSERTED line — a control nobody can check is decoration.
  3. Everything is scored in R. A fixed-% risk strategy compounds, so a dollar ranking measures
     recency rather than edge (root `CLAUDE.md` rule 6).
  4. `--server` names the broker whose cached bars were replayed, and it is printed with the bar
     count. Two brokers' gold histories differ in LENGTH, so a re-run on the other cache disagrees
     with every figure here while looking perfectly healthy.

**It reads each row's TRADE LIST, not just its KPIs**, through `run_sweep`'s `extract` hook — the
calendar split needs each trade's own entry time. It does NOT reproduce the bar loop: that loop
sets `bar_ms` off the frame and calls `finalize()` afterwards, and a copy forgetting either is
wrong in silence.

⚠ **Sweep in bar mode, validate the winner charged.** `--profile` charges a real broker tier
(spread + swap + commission) into every row, which is honest and slower; the rankings survive the
difference and the totals do not.

⚠ **A winner here is a CANDIDATE, never a default.** Adopting one is a commit across the config,
the Pine twin and its export, with the parity gate re-run green.

Usage:
    python backtest/tools/axis_sweep.py --strategy b_leg --split 2022-09-30 \\
        --server VantageMarkets_Demo --start 2018-09-13 --end 2026-08-05 \\
        --axis bleg_max_days=3,4,5,6 --axis exec_time_stop_hrs=4,6,8,12,18
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import importlib
import sys
from pathlib import Path
from typing import Any, List, Sequence, Tuple

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# A trade whose R is inside this band is a SCRATCH, not a win. Counting one as a win is a way of
# reporting a win rate that nobody's account recognises — the lab makes the same distinction.
_SCRATCH_R = 0.25


# ── what each combo sends back ───────────────────────────────────────────────────
# Module level because it is PICKLED to the worker processes. It returns plain tuples rather than
# Trade objects for the same reason: whatever this builds crosses a process boundary.
def _trade_rs(strategy) -> List[Tuple[int, float]]:
    return [(int(t.entry_ms), float(t.r)) for t in strategy.execution.trades]


# ── scoring, all of it in R ──────────────────────────────────────────────────────
def _mean_sd(rs: Sequence[float]) -> Tuple[float, float]:
    n = len(rs)
    if not n:
        return 0.0, 0.0
    m = sum(rs) / n
    if n < 2:
        return m, 0.0
    return m, (sum((r - m) ** 2 for r in rs) / (n - 1)) ** 0.5


def _max_dd_r(rs: Sequence[float]) -> float:
    """Peak-to-trough of the cumulative R curve. In R rather than dollars: at fixed-% risk a dollar
    drawdown is as much a leverage artefact as a result."""
    peak = cum = worst = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        worst = max(worst, peak - cum)
    return worst


def _pf(rs: Sequence[float]) -> float:
    gross = sum(r for r in rs if r > 0)
    loss = abs(sum(r for r in rs if r < 0))
    return gross / loss if loss > 0 else 0.0


class Row:
    """One swept value, scored."""

    def __init__(self, label: str, trades: Sequence[Tuple[int, float]], split_ms: int):
        self.label = label
        self.rs = [r for _ms, r in trades]
        self.is_rs = [r for ms, r in trades if ms < split_ms]
        self.oos_rs = [r for ms, r in trades if ms >= split_ms]

    @property
    def n(self) -> int:
        return len(self.rs)

    def cells(self) -> str:
        if not self.rs:
            return f"{self.label:<22} {0:>6}   — no trades —"
        m, sd = _mean_sd(self.rs)
        se = sd / len(self.rs) ** 0.5
        wins = sum(1 for r in self.rs if r > _SCRATCH_R)
        return (
            f"{self.label:<22} {self.n:>6} {sum(self.rs):>+9.2f} {m:>+8.3f} {se:>7.3f} "
            f"{_pf(self.rs):>6.2f} {-_max_dd_r(self.rs):>8.2f} {wins / self.n * 100:>5.1f}% "
            f"{sum(self.is_rs):>+8.2f} {sum(self.oos_rs):>+8.2f} "
            f"{sum(self.rs) - max(self.rs):>+9.2f}"
        )


_HEAD = (
    f"{'value':<22} {'trades':>6} {'sum R':>9} {'avg R':>8} {'+/-se':>7} {'PF':>6} "
    f"{'maxDD':>8} {'win%':>6} {'IS R':>8} {'OOS R':>8} {'ex-best':>9}"
)


# ── the config axis ──────────────────────────────────────────────────────────────
def _coerce(current: Any, raw: str) -> Any:
    """Coerce a command-line value to the field's EXISTING type, so `--axis flag=False` cannot
    quietly become the truthy string 'False'."""
    raw = raw.strip()
    if isinstance(current, bool):
        return raw.lower() in ("1", "true", "yes", "on")
    if isinstance(current, int) and not isinstance(current, bool):
        return int(float(raw))
    if isinstance(current, float):
        return float(raw)
    return raw


def _why_the_control_missed(pins: dict) -> str:
    """Name the FIRST suspect, and it is not always the harness.

    🔴 A `--pin` moves the control row itself: the baseline being replayed is the shipped config
    WITH that pin, so asserting the shipped bot's number against it fails every time and has
    nothing to do with the code. Saying "the harness has moved" there is a diagnostic reporting on
    a hypothesis rather than on what it found — the reader goes hunting a phantom, which is the
    trap root `CLAUDE.md` rule 5 is about. Pins are checked first BECAUSE they are the explanation
    the reader can act on immediately.
    """
    if pins:
        return (
            "\n\nFIRST SUSPECT: this run PINS "
            + ", ".join(f"{k}={v!r}" for k, v in pins.items())
            + ", and a pin applies to the control row too — so the baseline replayed here is NOT "
            "the shipped bot. Assert that pinned configuration's own number, or drop the pin. "
            "Only if the pins are irrelevant to the figure you stated has the harness moved."
        )
    return (
        "\n\nThe harness has moved since that baseline was recorded — find out what before "
        "reading any row here."
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--strategy", required=True, help="package under strategies/python/")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default=None, help="timeframe in minutes (default: the bot's own)")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument(
        "--split",
        required=True,
        help="YYYY-MM-DD — the out-of-sample boundary. REQUIRED, and stated before any row runs: "
        "a split chosen after seeing the grid is not a split.",
    )
    ap.add_argument(
        "--server",
        default=None,
        help="broker cache to replay (e.g. VantageMarkets_Demo). Omit only when the terminal you "
        "have attached IS the one you mean.",
    )
    ap.add_argument(
        "--axis",
        dest="axes",
        action="append",
        default=[],
        metavar="FIELD=v1,v2,...",
        help="one config field and the values to try. Repeatable; each axis is swept "
        "independently off the shipped defaults, never combined.",
    )
    ap.add_argument(
        "--pin",
        dest="pins",
        action="append",
        default=[],
        metavar="FIELD=VALUE",
        help="hold a field at a value for EVERY row including the control. Use it to state a "
        "basis, never to sneak a second axis in.",
    )
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument(
        "--profile",
        default=None,
        help="a key of backtest.fills.PROFILES — charges that tier's spread, swap and commission "
        "into every row. Omit for the free book.",
    )
    ap.add_argument("--expect-trades", type=int, default=None)
    ap.add_argument("--expect-r", type=float, default=None)
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args(argv)

    from backtest.data.source import BarSource
    from backtest.optimizer import Combo, run_sweep

    pkg = f"strategies.python.{args.strategy}"
    try:
        spec = importlib.import_module(pkg).LAB_STRATEGY
    except ImportError as exc:
        raise SystemExit(f"no strategy package {pkg!r}: {exc}")
    ConfigCls = spec["config"]

    tf = args.tf or str(spec.get("suggested_bar_value") or 15)
    split_ms = int(
        dt.datetime.strptime(args.split, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp()
        * 1000
    )

    cost_profile = None
    if args.profile:
        from backtest.fills import PROFILES

        if args.profile not in PROFILES:
            raise SystemExit(f"--profile {args.profile!r}: not in fills.PROFILES")
        cost_profile = PROFILES[args.profile]

    # ── the basis, printed BEFORE anything runs ──────────────────────────────────
    src = BarSource(server=args.server) if args.server else BarSource()
    df = src.load(args.symbol, tf, args.start, args.end)
    if df.empty:
        raise SystemExit("no bars returned for that window")

    base = ConfigCls(symbol=args.symbol)
    pins: dict = {}
    for p in args.pins:
        field, raw = p.split("=", 1)
        field = field.strip()
        if not hasattr(base, field):
            raise SystemExit(f"--pin {field!r}: no such field on {ConfigCls.__name__}")
        pins[field] = _coerce(getattr(base, field), raw)
    if pins:
        base = dataclasses.replace(base, **pins)

    print(f"strategy   {args.strategy}   ({ConfigCls.__name__})")
    print(f"bars       {len(df):,} {tf}m {args.symbol}   {df.index[0]} -> {df.index[-1]}")
    print(f"broker     {args.server or '(the attached terminal)'}")
    print(f"costs      {args.profile or 'NONE — free book'}")
    print(f"split      IS < {args.split} <= OOS   (declared before the grid ran)")
    if pins:
        print(f"pinned     {', '.join(f'{k}={v!r}' for k, v in pins.items())}")
    print()

    # ── build the combos: the control, then each axis one value at a time ────────
    combos: List[Combo] = [Combo(params={"__row": "CONTROL (shipped)"}, config=base)]
    for axis in args.axes:
        if "=" not in axis:
            raise SystemExit(f"--axis expects FIELD=v1,v2,..., got {axis!r}")
        field, raws = axis.split("=", 1)
        field = field.strip()
        if not hasattr(base, field):
            raise SystemExit(f"--axis {field!r}: no such field on {ConfigCls.__name__}")
        cur = getattr(base, field)
        for raw in raws.split(","):
            val = _coerce(cur, raw)
            combos.append(
                Combo(
                    params={"__row": f"{field}={val!r}", "__axis": field},
                    config=dataclasses.replace(base, **{field: val}),
                )
            )

    print(f"replaying {len(combos)} configurations ...", flush=True)
    rows = run_sweep(
        module_path=pkg,
        df=df,
        combos=combos,
        initial_capital=args.capital,
        max_workers=args.workers,
        cost_profile=cost_profile,
        extract=_trade_rs,
    )
    if len(rows) != len(combos):
        raise SystemExit(f"the sweep returned {len(rows)} rows for {len(combos)} combos")

    scored = [Row(r["params"]["__row"], r["extra"], split_ms) for r in rows]
    control = scored[0]

    # ── the control, asserted ────────────────────────────────────────────────────
    print()
    print(_HEAD)
    print("-" * len(_HEAD))
    print(control.cells())

    if args.expect_trades is not None and control.n != args.expect_trades:
        raise SystemExit(
            f"\nthe control made {control.n} trades, not the stated {args.expect_trades}. This "
            f"sweep is not replaying the bot the baseline describes, so no row under it can be "
            f"compared to anything." + _why_the_control_missed(pins)
        )
    if args.expect_r is not None and abs(sum(control.rs) - args.expect_r) > 0.01:
        raise SystemExit(
            f"\nthe control scored {sum(control.rs):+.2f}R, not the stated {args.expect_r:+.2f}R."
            + _why_the_control_missed(pins)
        )
    if args.expect_trades is None and args.expect_r is None:
        print(
            "  ^ CONTROL UNASSERTED — pass --expect-trades/--expect-r once a baseline exists, or "
            "this row proves nothing."
        )

    # ── the axes ─────────────────────────────────────────────────────────────────
    i = 1
    for axis in args.axes:
        field = axis.split("=", 1)[0].strip()
        n_vals = len(axis.split("=", 1)[1].split(","))
        print()
        print(f"  {field}   (shipped: {getattr(base, field)!r})")
        for row in scored[i : i + n_vals]:
            print("  " + row.cells())
        i += n_vals

    print()
    print("  avg R is the number to read. A row whose avg is smaller than ~2x its own standard")
    print("  error has not shown an edge, however good its total looks.")
    print("  IS / OOS split the SAME replay's trade list on entry time — it cannot change which")
    print("  trades exist. A value strong in one half and not the other is a story, not a setting.")
    print("  ex-best strips each row's single best trade. These strategies are fat-tailed by")
    print("  design, so one lucky runner can wear a whole configuration's name.")
    print("  Read a winner's NEIGHBOURS before believing it: a hill and a spike look identical")
    print("  from the top.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
