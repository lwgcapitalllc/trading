#!/usr/bin/env python3
"""realign_combo_study.py — which 5-minute structure sequence is worth trading?

Aaron's question (2026-09-11): on the 5m the market trends (SOS, then BOS), prints ONE counter
shift, then shifts back with the trend. Which version of that sequence is most profitable to
trade? This replays a fixed, pre-declared family of sequences through the Realign bot's own
"Chart frame" arm and exit ladder, costs charged, and grades every cell against a matched
random control.

THE FAMILY — 36 cells, declared here before any of them ran:

  at least 0 / 1 / 2 with-trend BOS before the counter shift     realign_min_trend_breaks
  at most 0 / 1 / any further counter BOS before realigning      realign_max_counter_breaks
  enter on the realigning shift, or on the next with-trend break realign_entry_on
  no trend filter, or the 15m structure must agree               realign_trend_minutes

plus one reference row: the shipped Realign setup (15m false break, 5m realignment).

WHAT IT ENFORCES rather than reminds you of:

  1. `--split` is REQUIRED and printed before anything runs. A split chosen after seeing the
     grid is not a split.
  2. Every cell is scored in R with costs charged, against a CONTROL: random entries matched on
     direction, stop distance, target distance, calendar month and hour of day, replayed
     through the SAME exit ladder and the same one position slot. Gold went 1,200 -> 4,300 over
     this window, so a long-biased rule looks good for free; the control is what removes that.
  3. A cell QUALIFIES only with >= 30 trades, positive in BOTH halves, and z >= 2 against its
     control. With 36 cells about one clears z >= 2 by luck alone, so the table also marks
     z >= 2.99 (the 5% family-wise bar) and prints every qualifier's NEIGHBOURS — a real
     setting sits on a hill, and a hill and a spike look identical from the top.
  4. `--broker` is a REQUIRED label: the bars come from a flat file that does not record which
     broker filled it, and two brokers' histories disagree while both look healthy.

⚠ Bars are the 5m frame RESAMPLED FROM M1 — the M5 cache is a trap (strategies/python/realign/
CLAUDE.md). ⚠ Risk is pinned to 1% on every row: R is scale-free and it keeps the venue lot
ceiling from ever binding. ⚠ A winner here is a CANDIDATE, never a default, and a LAB finding:
the chart-frame arm has no Pine counterpart and no parity gate yet.

Usage:
    python backtest/tools/realign_combo_study.py --broker VantageMarkets-Demo \\
        --split 2023-05-01 --profile puprime_ecn --out /tmp/study.json
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import importlib
import itertools
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from strategies.python.realign import RealignConfig, RealignStrategy  # noqa: E402
from strategies.python.realign.tracker import RealignState  # noqa: E402

_SELF = "backtest.tools.realign_combo_study"

# ── the grid, declared once ──────────────────────────────────────────────────────
K_TREND = (0, 1, 2)
J_COUNTER: Tuple[Optional[int], ...] = (0, 1, None)
ENTRY = ("Realigning shift", "Next break")
TREND: Tuple[Optional[int], ...] = (None, 15)

MIN_TRADES = 30
Z_CELL = 2.0
Z_FAMILY = 2.99  # one-sided 0.05 / 36
_SCRATCH_R = 0.25  # a trade inside this band is not a win (same band as axis_sweep.py)


# ── the control strategy ─────────────────────────────────────────────────────────
@dataclasses.dataclass(frozen=True)
class ControlConfig(RealignConfig):
    """The bot's config plus a SCHEDULE of forced entries: (bar_open_ms, dir, stop_dist,
    target_dist). Everything from the fill onward — sizing, costs, the exit ladder, the one
    position slot — is the real bot's, which is the whole point of the control."""

    control_schedule: tuple = ()


class _ScheduledTrigger:
    """A tracker that ignores structure and fires on the scheduled bars only."""

    def __init__(self, schedule, buf: float) -> None:
        self._sched = {int(ms): (int(d), float(sd), float(td)) for ms, d, sd, td in schedule}
        self._buf = buf
        self.close: Optional[float] = None

    def on_htf(self, *_a, **_k) -> None:
        return None

    def update(self, time_ms, high, low, ext, internal) -> RealignState:
        out = RealignState()
        s = self._sched.get(int(time_ms))
        if s is not None and self.close is not None:
            d, stop_dist, tgt_dist = s
            # The execution subtracts the stop buffer again, so add it here: the placed stop
            # then sits exactly `stop_dist` from this bar's close, like the real trade's.
            out.trigger_dir = d
            out.trigger_stop = self.close - d * stop_dist + d * self._buf
            out.trigger_target = self.close + d * tgt_dist
        return out


class ControlStrategy(RealignStrategy):
    def __init__(
        self,
        config=None,
        initial_capital: float = 1_000_000.0,
        tick_source=None,
        cost_profile=None,
        account=None,
        leg: str = "strat",
    ) -> None:
        super().__init__(
            config,
            initial_capital=initial_capital,
            tick_source=tick_source,
            cost_profile=cost_profile,
            account=account,
            leg=leg,
        )
        cfg = self.config
        self.tracker = _ScheduledTrigger(cfg.control_schedule, cfg.realign_sl_buf_tk * cfg.mintick)

    def _step_core(self, state, bar_time_ms: int):
        self.tracker.close = state.bar.close
        return super()._step_core(state, bar_time_ms)


LAB_STRATEGY = {"strategy": ControlStrategy, "config": ControlConfig}


# ── what each replay sends back (module level: it is pickled to the workers) ─────
def _trades(strategy) -> List[tuple]:
    """(entry_ms, exit_ms, dir, r, stop_distance, target_distance) per closed trade."""
    out = []
    for t in strategy.execution.trades:
        tp2 = getattr(t, "tp2", None)
        tgt = (float(tp2) - float(t.entry_price)) * int(t.dir) if tp2 else None
        out.append(
            (int(t.entry_ms), int(t.exit_ms), int(t.dir), float(t.r), float(t.stop_distance), tgt)
        )
    return out


# ── bars ─────────────────────────────────────────────────────────────────────────
def _load_5m(m1_csv: Path, start: str, end: str):
    import pandas as pd

    if not m1_csv.exists():
        raise SystemExit(f"no M1 bars at {m1_csv}")
    df = pd.read_csv(m1_csv, usecols=["time", "open", "high", "low", "close"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time").sort_index().loc[start : end + " 23:59:59"]
    return (
        df.resample("5min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )


# ── the grid ─────────────────────────────────────────────────────────────────────
def _cells() -> List[tuple]:
    return list(itertools.product(K_TREND, J_COUNTER, ENTRY, TREND))


def _label(cell) -> str:
    k, j, e, t = cell
    jj = "any" if j is None else str(j)
    ee = "shift" if e == ENTRY[0] else "next"
    tt = "15m" if t else "-"
    return f"trend>={k} ctr<={jj:<3} {ee:<5} {tt:<3}"


def _cell_config(base: RealignConfig, cell) -> RealignConfig:
    k, j, e, t = cell
    return dataclasses.replace(
        base,
        realign_arm_frame="Chart frame",
        realign_min_trend_breaks=k,
        realign_max_counter_breaks=j,
        realign_entry_on=e,
        realign_trend_minutes=t,
    )


def _neighbours(cell) -> List[tuple]:
    k, j, e, t = cell
    out = []
    ki, ji = K_TREND.index(k), J_COUNTER.index(j)
    for dk in (-1, 1):
        if 0 <= ki + dk < len(K_TREND):
            out.append((K_TREND[ki + dk], j, e, t))
    for dj in (-1, 1):
        if 0 <= ji + dj < len(J_COUNTER):
            out.append((k, J_COUNTER[ji + dj], e, t))
    out.append((k, j, ENTRY[1 - ENTRY.index(e)], t))
    out.append((k, j, e, TREND[1 - TREND.index(t)]))
    return out


# ── the control schedule ─────────────────────────────────────────────────────────
def _buckets(index, lo: int, hi: int):
    """Bar open times grouped by (year, month, hour) and by (year, month)."""
    ms = index.asi8 // 1_000_000
    yrs, mos, hrs = index.year, index.month, index.hour
    by_mh, by_m = defaultdict(list), defaultdict(list)
    for i in range(lo, hi):
        by_mh[(yrs[i], mos[i], hrs[i])].append(int(ms[i]))
        by_m[(yrs[i], mos[i])].append(int(ms[i]))
    return by_mh, by_m


def _schedule(trades, by_mh, by_m, rnd: random.Random) -> List[tuple]:
    """One random entry per real trade: same direction, stop and target distance, same
    calendar month and hour of day. A trade with no target distance is skipped."""
    out, used = [], set()
    for entry_ms, _exit, d, _r, stop_dist, tgt in trades:
        if tgt is None or stop_dist <= 0:
            continue
        ts = dt.datetime.fromtimestamp(entry_ms / 1000, tz=dt.timezone.utc)
        pool = by_mh.get((ts.year, ts.month, ts.hour)) or by_m.get((ts.year, ts.month))
        if not pool:
            continue
        for _ in range(10):
            ms = rnd.choice(pool)
            if ms not in used:
                used.add(ms)
                out.append((ms, d, stop_dist, tgt))
                break
    return out


# ── scoring, all of it in R ──────────────────────────────────────────────────────
def _mean_sd(rs: Sequence[float]) -> Tuple[float, float]:
    n = len(rs)
    if not n:
        return 0.0, 0.0
    m = sum(rs) / n
    if n < 2:
        return m, 0.0
    return m, (sum((r - m) ** 2 for r in rs) / (n - 1)) ** 0.5


def _max_dd(rs: Sequence[float]) -> float:
    peak = cum = worst = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        worst = max(worst, peak - cum)
    return worst


def _pf(rs: Sequence[float]) -> float:
    gross = sum(r for r in rs if r > 0)
    loss = abs(sum(r for r in rs if r < 0))
    return gross / loss if loss > 0 else float("inf") if gross > 0 else 0.0


def _welch_z(a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    if len(a) < 2 or len(b) < 2:
        return None
    ma, sa = _mean_sd(a)
    mb, sb = _mean_sd(b)
    se = (sa * sa / len(a) + sb * sb / len(b)) ** 0.5
    return (ma - mb) / se if se > 0 else None


def _stats(trades, split_ms: int, ctrl_rs: Sequence[float]) -> dict:
    tr = sorted(trades, key=lambda t: t[1])  # exit order: the order the account felt them
    rs = [t[3] for t in tr]
    n = len(rs)
    m, sd = _mean_sd(rs)
    cm, _ = _mean_sd(ctrl_rs)
    return {
        "n": n,
        "sum_r": sum(rs),
        "avg_r": m,
        "se": sd / n**0.5 if n else 0.0,
        "pf": _pf(rs),
        "max_dd": _max_dd(rs),
        "win_pct": 100.0 * sum(1 for r in rs if r > _SCRATCH_R) / n if n else 0.0,
        "is_r": sum(t[3] for t in tr if t[0] < split_ms),
        "oos_r": sum(t[3] for t in tr if t[0] >= split_ms),
        "long_r": sum(t[3] for t in tr if t[2] > 0),
        "short_r": sum(t[3] for t in tr if t[2] < 0),
        "ex_best": sum(rs) - max(rs) if rs else 0.0,
        "ctrl_n": len(ctrl_rs),
        "ctrl_avg_r": cm,
        "z": _welch_z(rs, ctrl_rs),
        "rs": rs,
    }


def _qualifies(s: dict) -> bool:
    return (
        s["n"] >= MIN_TRADES
        and s["is_r"] > 0
        and s["oos_r"] > 0
        and s["z"] is not None
        and s["z"] >= Z_CELL
    )


_HEAD = (
    f"{'cell':<27} {'n':>4} {'sum R':>8} {'avg R':>7} {'PF':>5} {'maxDD':>6} "
    f"{'win%':>5} {'IS R':>7} {'OOS R':>7} {'long R':>7} {'short R':>7} {'ex-best':>8} "
    f"{'ctrl R':>7} {'z':>5}  flags"
)


def _cells_line(label: str, s: dict) -> str:
    if not s["n"]:
        return f"{label:<27} {0:>4}   — no trades —"
    z = "  n/a" if s["z"] is None else f"{s['z']:>5.2f}"
    flags = []
    if s["n"] < MIN_TRADES:
        flags.append("thin")
    if s["is_r"] <= 0 or s["oos_r"] <= 0:
        flags.append("one-half")
    if _qualifies(s):
        flags.append("QUALIFIES" + ("*" if s["z"] >= Z_FAMILY else ""))
    pf = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    return (
        f"{label:<27} {s['n']:>4} {s['sum_r']:>+8.2f} {s['avg_r']:>+7.3f} {pf:>5} "
        f"{-s['max_dd']:>6.2f} {s['win_pct']:>4.1f}% {s['is_r']:>+7.2f} {s['oos_r']:>+7.2f} "
        f"{s['long_r']:>+7.2f} {s['short_r']:>+7.2f} {s['ex_best']:>+8.2f} "
        f"{s['ctrl_avg_r']:>+7.3f} {z}  {' '.join(flags)}"
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--m1-csv", default=str(_ROOT / "backtest" / "cache" / "XAUUSD__M1.csv"))
    ap.add_argument(
        "--broker", required=True, help="whose M1 bars these are (the flat file does not record it)"
    )
    ap.add_argument("--start", default="2020-01-02")
    ap.add_argument("--end", default="2026-08-06")
    ap.add_argument("--split", required=True, help="YYYY-MM-DD — the out-of-sample boundary")
    ap.add_argument(
        "--profile",
        default="puprime_ecn",
        help="a key of backtest.fills.PROFILES, or 'none' for the free book",
    )
    ap.add_argument("--seeds", type=int, default=3, help="control replays per cell")
    ap.add_argument("--risk-pct", type=float, default=1.0)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--out", default=None, help="write every row and its R list here (JSON)")
    args = ap.parse_args(argv)

    from backtest.fills import PROFILES
    from backtest.optimizer import Combo, run_sweep

    # The control classes must be pickled by their IMPORTABLE path, never as `__main__.X`.
    me = importlib.import_module(_SELF)
    cost_profile = None
    if args.profile != "none":
        if args.profile not in PROFILES:
            raise SystemExit(f"--profile {args.profile!r}: not in fills.PROFILES")
        cost_profile = PROFILES[args.profile]
    split_ms = int(
        dt.datetime.strptime(args.split, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp()
        * 1000
    )

    df = _load_5m(Path(args.m1_csv), args.start, args.end)
    print(f"bars     {len(df):,} 5m (resampled from M1)   {df.index[0]} -> {df.index[-1]}")
    print(f"broker   {args.broker}   (bars)   costs {args.profile}")
    print(f"split    IS < {args.split} <= OOS   (declared before the grid ran)")
    print(
        f"risk     {args.risk_pct}% per trade, ${args.capital:,.0f} start   "
        f"controls {args.seeds} per cell"
    )
    print(
        f"qualify  n >= {MIN_TRADES}, both halves > 0, z >= {Z_CELL} "
        f"(* = z >= {Z_FAMILY}, the family-wise bar for 36 cells)\n",
        flush=True,
    )

    base = dataclasses.replace(RealignConfig(), exec_risk_pct=args.risk_pct)
    cells = _cells()
    combos = [Combo(params={"row": "SHIPPED (15m false break)"}, config=base)]
    combos += [Combo(params={"row": _label(c)}, config=_cell_config(base, c)) for c in cells]

    t0 = time.time()
    print(f"replaying {len(combos)} configurations ...", flush=True)
    rows = run_sweep(
        module_path="strategies.python.realign",
        df=df,
        combos=combos,
        initial_capital=args.capital,
        max_workers=args.workers,
        cost_profile=cost_profile,
        extract=me._trades,
    )
    if len(rows) != len(combos):
        raise SystemExit(f"the sweep returned {len(rows)} rows for {len(combos)} configurations")
    print(f"  done in {time.time() - t0:.0f}s", flush=True)

    # ── the controls ─────────────────────────────────────────────────────────────
    by_mh, by_m = _buckets(df.index, 3000, len(df) - 300)
    ctrl_fields = [f.name for f in dataclasses.fields(RealignConfig)]
    ctrl_combos = []
    for ri, (combo, row) in enumerate(zip(combos, rows)):
        cfg = dataclasses.replace(
            combo.config,
            realign_arm_frame="Chart frame",
            realign_min_trend_breaks=0,
            realign_max_counter_breaks=None,
            realign_entry_on="Realigning shift",
            realign_trend_minutes=None,
            realign_pattern="any",
            realign_long_source="swing",
            realign_short_source="swing",
        )
        for s in range(args.seeds):
            sched = _schedule(row["extra"], by_mh, by_m, random.Random(1000 * ri + s))
            if not sched:
                continue
            ccfg = me.ControlConfig(
                **{n: getattr(cfg, n) for n in ctrl_fields}, control_schedule=tuple(sched)
            )
            ctrl_combos.append(Combo(params={"row_i": ri, "seed": s}, config=ccfg))

    t1 = time.time()
    print(f"replaying {len(ctrl_combos)} control books ...", flush=True)
    ctrl_rows = run_sweep(
        module_path=_SELF,
        df=df,
        combos=ctrl_combos,
        initial_capital=args.capital,
        max_workers=args.workers,
        cost_profile=cost_profile,
        extract=me._trades,
    )
    print(f"  done in {time.time() - t1:.0f}s\n", flush=True)
    ctrl_rs = defaultdict(list)
    for cr in ctrl_rows:
        ctrl_rs[cr["params"]["row_i"]].extend(t[3] for t in cr["extra"])

    # ── the table ────────────────────────────────────────────────────────────────
    stats = [_stats(row["extra"], split_ms, ctrl_rs[i]) for i, row in enumerate(rows)]
    by_cell = {c: stats[i + 1] for i, c in enumerate(cells)}
    print(_HEAD)
    print("-" * len(_HEAD))
    print(_cells_line(rows[0]["params"]["row"], stats[0]))
    print()
    for c in cells:
        print(_cells_line(_label(c), by_cell[c]))

    quals = [c for c in cells if _qualifies(by_cell[c])]
    quals.sort(
        key=lambda c: (
            -(
                by_cell[c]["sum_r"] / by_cell[c]["max_dd"]
                if by_cell[c]["max_dd"] > 0
                else float("inf")
            )
        )
    )
    print(f"\nQUALIFIERS, ranked by R per unit of drawdown ({len(quals)} of {len(cells)}):")
    if not quals:
        print("  none — no cell cleared all three bars.")
    for c in quals:
        s = by_cell[c]
        nb = [by_cell[x]["sum_r"] for x in _neighbours(c)]
        rdd = s["sum_r"] / s["max_dd"] if s["max_dd"] > 0 else float("inf")
        print(
            f"  {_label(c)}  {s['sum_r']:+.2f}R  R/DD {rdd:.2f}  z {s['z']:.2f}  "
            f"neighbours {', '.join(f'{x:+.1f}' for x in nb)}  "
            f"(all positive: {all(x > 0 for x in nb)})"
        )

    if args.out:
        payload = {
            "command": " ".join(sys.argv),
            "bars": len(df),
            "first": str(df.index[0]),
            "last": str(df.index[-1]),
            "broker": args.broker,
            "profile": args.profile,
            "split": args.split,
            "risk_pct": args.risk_pct,
            "seeds": args.seeds,
            "shipped": stats[0],
            "cells": [{"cell": list(c), "label": _label(c), **by_cell[c]} for c in cells],
            "qualifiers": [_label(c) for c in quals],
        }
        Path(args.out).write_text(json.dumps(payload, default=str))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
