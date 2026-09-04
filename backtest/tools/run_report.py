#!/usr/bin/env python3
"""run_report.py — replay a Python strategy over YEARS of broker bars and report
WHY it made or lost money, not just how much.

The TradingView Strategy Tester answers "what did it make". It cannot answer "under
what conditions did the edge stop working", for two reasons: its chart-data export is
capped to the bars your plan loads (~11 months on 15m), and its trade list carries no
market context at all. This tool has neither limit — it pulls bars straight from the
broker via the MT5 agent, replays them through the canonical `engines/`, and tags every
trade with the context it was taken in.

It emits three things:

  trades.csv   one row per completed trade, with the market REGIME at entry, the NY
               session and hour, the excursion (how far it ran for and against), and
               the R it booked. This is the file that answers "what kind of market
               loses money".

  setups.csv   one row per SOS Fade leg that reached the SOS stage, whether it traded or
               not, and what it was missing if it didn't. Blocked and skipped setups
               leave NO record in a broker trade list — no order is placed, so nothing
               exists to export. This is the only place they are countable.

  stdout       a per-year and per-regime summary, in R.

R, not dollars: this strategy risks a fixed % of equity, so the same edge earns
exponentially more dollars as the account grows. Reading the dollar curve makes a flat
early year look like a broken edge when it was the same edge on a smaller account.

Usage:
    python backtest/tools/run_report.py                       # XAUUSD 15m, full broker history
    python backtest/tools/run_report.py --start 2022-05-09 --end 2026-07-25
    python backtest/tools/run_report.py --strategy b_leg --out /tmp/bleg
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

NY = ZoneInfo("America/New_York")

# The strategy packages this tool knows how to drive. Each one declares LAB_STRATEGY
# (the lab's own contract), so we read the class + config from there rather than
# hardcoding either — a new Python strategy becomes runnable here for free.
_STRATEGIES = {
    "sos_fade": "strategies.python.sos_fade",
    "b_leg": "strategies.python.b_leg",
    "realign": "strategies.python.realign",
}


# ── market context ───────────────────────────────────────────────────────────────
# Everything below is REPORTING. None of it is fed back into the strategy, so adding
# or changing a tag can never move a trade — the run is identical with or without it.


def _session(hour_ny: int) -> str:
    """Which session the entry landed in, by NY hour. Matches the session windows the
    Pine draws (Tokyo 20-05, London 04-13, NY 09-18) — overlaps resolve to the one
    that owns the hour for trading purposes."""
    if 20 <= hour_ny or hour_ny < 4:
        return "Asia"
    if 4 <= hour_ny < 9:
        return "London"
    if 9 <= hour_ny < 18:
        return "NewYork"
    return "Late"


def _regime_at(df, i: int, cache: dict) -> str:
    """The canonical regime classifier's label at bar `i`.

    `engines/regime/` is the ONE implementation (repo rule) — imported, never
    reimplemented. It wants a short frame and a long frame; we give it the trailing
    15m window and the same window resampled up to H4, which is the pairing the live
    bots use. Results are memoised per 4-hour bucket: the classifier reads 34+ bars of
    slowly-moving averages, so recomputing it for two trades an hour apart returns the
    same label at real cost.
    """
    bucket = i // 16  # 16 x 15m = one H4 bar
    if bucket in cache:
        return cache[bucket]
    from engines.regime.classifier import classify_regime

    # 34 H4 bars is the classifier's stated minimum; 1000 15m bars gives ~62 with room
    # for the market's closed hours.
    lo = max(0, i - 1000)
    window = df.iloc[lo : i + 1]
    if len(window) < 200:
        cache[bucket] = "UNKNOWN"
        return cache[bucket]
    long_df = (
        window.resample("4h")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )
    label = classify_regime(window.tail(200), long_df)
    cache[bucket] = label
    return label


# ── setup reconstruction ─────────────────────────────────────────────────────────


class Leg:
    """One SOS Fade leg that reached the SOS stage, tracked across the bars it was alive.

    The strategy clears its own per-leg state the instant a leg dies, so a leg's story
    has to be assembled while it is running. A leg is a RUN of consecutive bars where
    the side's stage is 2 or higher; it ends when the stage falls back below 2.
    """

    __slots__ = (
        "dir",
        "start",
        "end",
        "stage_max",
        "edge_ever",
        "veto_ever",
        "armed_ever",
        "traded",
        "edge_first",
    )

    def __init__(self, direction: int, start: int):
        self.dir = direction
        self.start = start
        self.end = start
        self.stage_max = 0
        self.edge_ever = False
        self.veto_ever = False
        self.armed_ever = False
        self.traded = False
        self.edge_first = None

    def verdict(self) -> str:
        """What actually stopped this leg becoming a trade — the FIRST thing that did,
        so a leg is never blamed on a gate it never reached."""
        if self.traded:
            return "traded"
        if self.stage_max < 3:
            return "never retraced to 0.5"
        if not self.edge_ever:
            return "no FVG in the zone"
        if self.veto_ever:
            return "divergence / extreme-RSI veto"
        if not self.armed_ever:
            return "arm source disabled"
        return "limit rested, never filled"


def _collect_legs(decisions) -> list[Leg]:
    legs: list[Leg] = []
    live: dict[int, Leg] = {}
    for d in decisions:
        for direction, stage, edge, veto, armed in (
            (1, d.l_stage, d.long_edge, d.long_veto, d.long_armed),
            (-1, d.s_stage, d.short_edge, d.short_veto, d.short_armed),
        ):
            leg = live.get(direction)
            if stage >= 2:
                if leg is None:
                    leg = Leg(direction, d.index)
                    live[direction] = leg
                    legs.append(leg)
                leg.end = d.index
                leg.stage_max = max(leg.stage_max, stage)
                leg.veto_ever = leg.veto_ever or veto
                leg.armed_ever = leg.armed_ever or armed
                if edge is not None:
                    leg.edge_ever = True
                    if leg.edge_first is None:
                        leg.edge_first = edge
            elif leg is not None:
                live.pop(direction, None)
        # An entry fill belongs to whichever leg is live on that side.
        for f in d.fills:
            if f.kind == "entry":
                leg = live.get(f.dir)
                if leg is not None:
                    leg.traded = True
    return legs


# ── reporting ────────────────────────────────────────────────────────────────────


def _choose_replay(cfg, no_secondary: bool):
    """Decide which replay path the config actually needs. Returns `(cfg, wants_secondary, note)`.

    Pure so it can be tested without bars, a terminal or a strategy.

    🔴 The rule it enforces: **the config that gets REPORTED must be the config that RAN.**
    `--no-secondary` does not merely pick the fast path, it sets `exec_secondary=False`, because
    a run whose stored config says True while the 15m-only path executed is a run that lies about
    itself — and that is precisely the state every `run_report.py` run was in before 2026-08-16.
    """
    wants = bool(getattr(cfg, "exec_secondary", False))
    if not (wants and no_secondary):
        return cfg, wants, ""
    import dataclasses

    return (
        dataclasses.replace(cfg, exec_secondary=False),
        False,
        "--no-secondary: exec_secondary forced False (the 15m-only path is what runs)",
    )


def _assert_timeframe(df, tf: str) -> None:
    """Refuse to replay bars that are not the timeframe we asked for.

    MT5 does NOT error when a symbol has no history at the requested timeframe — it
    hands back the nearest COARSER one, still labelled as what you asked for. Measured
    on Vantage XAUUSD 2026-07-26: asking for M15 before 2018-09-14 returns hourly bars
    (23/day) or a single daily bar, indistinguishable from real data by inspection.

    A backtest fed daily bars as 15m does not crash. It produces a full set of trades,
    a clean equity curve, and a completely fictional answer — which is far worse than an
    exception. The bar SPACING is the one thing that cannot lie, so check that.
    """
    if len(df.index) < 3:
        raise SystemExit(f"only {len(df.index)} bars returned — nothing to replay")
    want_min = int(tf) if str(tf).isdigit() else None
    if want_min is None:
        return
    gaps = df.index.to_series().diff().dropna()
    # The modal gap is the timeframe; weekends and the daily close break produce larger
    # ones, and no legitimate gap is ever SMALLER than the bar interval.
    modal_min = int(gaps.mode().iloc[0].total_seconds() // 60)
    if modal_min != want_min:
        raise SystemExit(
            f"REFUSING TO RUN: asked for {want_min}m bars, but the most common spacing in "
            f"the returned data is {modal_min}m. MT5 silently substitutes a coarser "
            f"timeframe when it has no history at the one requested — this window starts "
            f"before the broker's real {want_min}m history. Move --start later."
        )
    off_tf = int((gaps < pd.Timedelta(minutes=want_min)).sum())
    if off_tf:
        raise SystemExit(f"REFUSING TO RUN: {off_tf} bars are spaced closer than {want_min}m")


def _default_start(symbol: str, tf: str) -> str:
    """The earliest date this broker has REAL bars at this timeframe — measured, not typed.

    A hardcoded default here is wrong in both directions. Too early and MT5 serves coarser
    bars mislabelled as the timeframe asked for (`_assert_timeframe` catches that, but only
    after a long load). Too late and years of real history go silently unused — which is the
    quieter failure, because the run looks perfectly healthy while answering a narrower
    question than the one asked. This tool shipped with a fixed "2022-01-01", so every
    default run reported 4.6 years of a 7.9-year history and said nothing about it.

    `floor_for` returns None when the attached broker cannot be identified (agent down), and
    an unknown broker's depth is not something to guess at — say so and ask for `--start`.
    """
    from backtest.data.history import floor_for

    fl = floor_for(symbol, tf)
    if fl is None:
        raise SystemExit(
            f"cannot measure the broker's earliest {tf}m history for {symbol} — the MT5 agent "
            f"is unreachable, so the attached broker is unknown and no floor applies. Pass "
            f"--start YYYY-MM-DD explicitly (guessing one here would risk a fictional run)."
        )
    return fl.isoformat()


def _grade(r: float, band: float) -> str:
    if abs(r) <= band:
        return "be"
    return "win" if r > 0 else "loss"


def _summary(label: str, rows: list[dict], band: float) -> str:
    if not rows:
        return f"{label:<16} —"
    rs = [r["r"] for r in rows]
    g = [_grade(r["r"], band) for r in rows]
    wins = [r["r"] for r, k in zip(rows, g) if k == "win"]
    losses = [r["r"] for r, k in zip(rows, g) if k == "loss"]
    return (
        f"{label:<16} n={len(rows):4d}  sumR={sum(rs):8.1f}  avgR={statistics.mean(rs):6.2f}  "
        f"win={len(wins):3d} loss={len(losses):3d} be={g.count('be'):3d}  "
        f"wr={100 * len(wins) / len(rows):3.0f}%  "
        f"avgWin={statistics.mean(wins) if wins else 0:5.2f}  "
        f"avgLoss={statistics.mean(losses) if losses else 0:6.2f}"
    )


def _by(rows: list[dict], key: str, band: float, title: str) -> None:
    print(f"\n--- {title} ---")
    groups = defaultdict(list)
    for r in rows:
        groups[r[key]].append(r)
    for k in sorted(groups):
        print(_summary(str(k), groups[k], band))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--strategy", default="sos_fade", choices=sorted(_STRATEGIES))
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="15", help="target timeframe in minutes")
    ap.add_argument(
        "--start",
        default=None,
        help="YYYY-MM-DD (default: the broker's measured earliest bar at this "
        "timeframe, from backtest/data/history.py)",
    )
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument(
        "--warmup",
        type=int,
        default=1000,
        help="bars the engines warm on before decisions are recorded",
    )
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument(
        "--fill-model",
        default="bar",
        choices=["bar", "tick"],
        help="'bar' = zero-cost Pine-equivalent guess; 'tick' = real fills + costs",
    )
    ap.add_argument(
        "--out", default=None, help="output directory (default: backtest/reports/<stamp>)"
    )
    ap.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        metavar="FIELD=VALUE",
        help="override a config field, e.g. --set exec_trail_step=2.0. Repeatable. "
        "The field must already exist on the strategy's config — a typo raises "
        "rather than silently running the default, which would make the run a lie.",
    )
    ap.add_argument(
        "--no-regime",
        action="store_true",
        help="skip the regime tag (faster; drops the 'what market' answer)",
    )
    ap.add_argument(
        "--no-secondary",
        action="store_true",
        help="force the 15m-only replay even if the config wants the 1m secondary. It also "
        "SETS exec_secondary=False, so the config that is reported is the one that ran.",
    )
    args = ap.parse_args(argv)

    import importlib

    from backtest.data.source import BarSource

    mod = importlib.import_module(_STRATEGIES[args.strategy])
    spec = mod.LAB_STRATEGY
    StrategyCls, ConfigCls = spec["strategy"], spec["config"]

    start = args.start or _default_start(args.symbol, args.tf)
    end = args.end or dt.date.today().isoformat()

    print(f"loading {args.symbol} {args.tf}m  {start} -> {end} ...", flush=True)
    df = BarSource().load(args.symbol, args.tf, start, end)
    if df.empty:
        print("no bars returned — is the MT5 agent tunnel up on localhost:8766?")
        return 1
    print(f"  {len(df):,} bars  {df.index[0]} -> {df.index[-1]}", flush=True)
    _assert_timeframe(df, args.tf)

    cfg = ConfigCls(fill_model=args.fill_model, symbol=args.symbol)
    # The config is a FROZEN dataclass (deliberately — a strategy input must not drift
    # mid-run), so overrides are collected and applied with one `replace`.
    patch: dict = {}
    for ov in args.overrides:
        if "=" not in ov:
            raise SystemExit(f"--set expects FIELD=VALUE, got {ov!r}")
        field, raw = ov.split("=", 1)
        field = field.strip()
        if not hasattr(cfg, field):
            raise SystemExit(f"--set {field!r}: no such config field on {ConfigCls.__name__}")
        cur = getattr(cfg, field)
        # Coerce to the existing field's type so "--set exec_no_late_day=False" cannot
        # silently become the truthy string "False".
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
    if patch:
        import dataclasses

        cfg = dataclasses.replace(cfg, **patch)
    # ── which REPLAY PATH ────────────────────────────────────────────────────────
    # 🔴 `exec_secondary` fills and manages on real 1m bars through `run_dual(df15, df1m)`.
    # `run(df15)` cannot execute one no matter what the flag says, and until 2026-08-16 this
    # tool always called `run()` — so every run it has ever produced for `sos_fade` was
    # primary-only while the config said `exec_secondary=True` (its DEFAULT). It printed
    # "override exec_secondary = True" and exited 0. MEASURED on full history, 2018-09-14 →
    # 2026-08-14: the dual path books 8 secondary trades worth +25.5R that the 15m-only path
    # cannot see (189 trades / 164.4R vs 182 / 140.0R).
    #
    # ⚠ THIS MOVES DOCUMENTED BASELINES. Any figure in
    # `strategies/python/sos_fade/sos_fade_optimization.md` produced by this tool at
    # the default config is a PRIMARY-ONLY number. They are not wrong as a matched set — every
    # combo in a sweep was missing the secondary equally, so the RANKINGS stand — but the
    # absolute totals understate. Re-run before quoting one as this bot's result.
    #
    # The refusal shape is `portfolio/legs.py`'s, which already refuses `exec_secondary` for
    # this exact reason. Here we can do better than refuse, because the 1m frame is loadable.
    cfg, wants_secondary, note = _choose_replay(cfg, args.no_secondary)
    if note:
        print(f"  {note}")

    strat = StrategyCls(config=cfg, initial_capital=args.capital)

    if wants_secondary:
        if not hasattr(strat, "run_dual"):
            # Never silently downgrade to the primary-only path — that is the whole defect.
            raise SystemExit(
                f"{args.strategy} sets exec_secondary=True but has no run_dual(), so its 1m "
                f"re-entries cannot be replayed. Pass --no-secondary to measure the primary "
                f"alone (it will set the flag False so the reported config matches the run)."
            )
        # WHICH feed the re-entry's resting order is filled against — the STRATEGY owns it
        # (`exec_sec_fill_tf_min`, 5 by default since 2026-08-21), because it is the thing that
        # knows what its own order needs. Hardcoding 1 here loaded 2.8M bars for 1.3% of accuracy
        # over 5m, on every run, for as long as this tool existed. A strategy that does not
        # declare one keeps the old 1m behaviour rather than being quietly coarsened.
        fill_tf = int(getattr(cfg, "exec_sec_fill_tf_min", 1) or 1)
        print(
            f"loading {args.symbol} {fill_tf}m for the secondary  {start} -> {end} ...", flush=True
        )
        df1m = BarSource().load(args.symbol, fill_tf, start, end)
        if df1m.empty:
            raise SystemExit(
                f"exec_secondary=True but no {fill_tf}m bars came back for that window. Refusing "
                f"rather than running the 15m-only path, which would silently drop every "
                f"re-entry. Pass --no-secondary to measure the primary alone."
            )
        print(f"  {len(df1m):,} bars  {df1m.index[0]} -> {df1m.index[-1]}", flush=True)
        _assert_timeframe(df1m, fill_tf)
        print(
            f"replaying {args.strategy} DUAL 15m+{fill_tf}m (warmup {args.warmup}) ...",
            flush=True,
        )
        strat.run_dual(df, df1m, warmup=args.warmup)
    else:
        print(f"replaying {args.strategy} (warmup {args.warmup}) ...", flush=True)
        strat.run(df, warmup=args.warmup)

    trades = strat.execution.trades
    legs = _collect_legs(strat.decisions)
    band = getattr(cfg, "exec_scratch_r", 0.15)
    # Count the secondaries explicitly. "0 secondary trades" on a dual run is a real answer
    # (the 1m SOS never armed); the absence of this line is what let a dead feed look the same.
    n_sec = sum(1 for t in trades if getattr(t, "kind", "primary") == "secondary")
    sec_note = (
        f", {n_sec} of them secondary (1m re-entries)"
        if wants_secondary
        else ", primary only (no 1m secondary in this run)"
    )
    print(f"  {len(trades)} trades{sec_note}, {len(legs)} SOS Fade legs reached SOS", flush=True)

    out = (
        Path(args.out)
        if args.out
        else _ROOT / "backtest" / "reports" / dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    )
    out.mkdir(parents=True, exist_ok=True)

    # ── trades.csv ──
    regime_cache: dict = {}
    rows: list[dict] = []
    for t in trades:
        ts = df.index[t.entry_index] if t.entry_index < len(df.index) else df.index[-1]
        ny = ts.tz_localize("UTC").tz_convert(NY) if ts.tzinfo is None else ts.astimezone(NY)
        rows.append(
            {
                "entry_utc": ts.isoformat(),
                "entry_ny": ny.strftime("%Y-%m-%d %H:%M"),
                "year": ny.year,
                "month": f"{ny.month:02d}",
                "weekday": ny.strftime("%a"),
                "hour_ny": f"{ny.hour:02d}",
                "session": _session(ny.hour),
                "regime": "off" if args.no_regime else _regime_at(df, t.entry_index, regime_cache),
                "dir": "long" if t.dir > 0 else "short",
                "r": round(t.r, 3),
                "grade": _grade(t.r, band),
                "pnl_usd": round(t.pnl_usd, 2),
                "entry_price": round(t.entry_price, 2),
                "exit_price": round(t.exit_price, 2),
                "stop_distance": round(t.stop_distance, 2),
                "bars_held": t.exit_index - t.entry_index,
                "mfe_usd": round(t.mfe_usd, 2),
                "mae_usd": round(t.mae_usd, 2),
                "mfe_r": round(t.mfe_usd / t.risk_usd, 3) if t.risk_usd else 0.0,
                "mae_r": round(t.mae_usd / t.risk_usd, 3) if t.risk_usd else 0.0,
                "exit_reason": t.exit_reason,
                "costs_usd": round(t.costs_usd, 2),
            }
        )
    if rows:
        with open(out / "trades.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    # ── setups.csv ──
    leg_rows = []
    for lg in legs:
        ts = df.index[min(lg.start, len(df.index) - 1)]
        ny = ts.tz_localize("UTC").tz_convert(NY) if ts.tzinfo is None else ts.astimezone(NY)
        leg_rows.append(
            {
                "sos_utc": ts.isoformat(),
                "year": ny.year,
                "hour_ny": f"{ny.hour:02d}",
                "session": _session(ny.hour),
                "dir": "long" if lg.dir > 0 else "short",
                "bars_alive": lg.end - lg.start,
                "stage_max": lg.stage_max,
                "reached_zone": lg.stage_max >= 3,
                "edge_ever": lg.edge_ever,
                "veto_ever": lg.veto_ever,
                "armed_ever": lg.armed_ever,
                "traded": lg.traded,
                "verdict": lg.verdict(),
                "edge_price": round(lg.edge_first, 2) if lg.edge_first is not None else "",
            }
        )
    if leg_rows:
        with open(out / "setups.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(leg_rows[0]))
            w.writeheader()
            w.writerows(leg_rows)

    # ── stdout ──
    print("\n" + "=" * 108)
    print(
        f"{args.strategy}  {args.symbol} {args.tf}m   {df.index[0].date()} -> {df.index[-1].date()}"
        f"   fill={args.fill_model}   breakeven band ±{band}R"
    )
    print("=" * 108)
    if rows:
        print("\n" + _summary("ALL", rows, band))
        _by(rows, "year", band, "BY YEAR")
        _by(rows, "regime", band, "BY REGIME AT ENTRY")
        _by(rows, "session", band, "BY SESSION")
        _by(rows, "dir", band, "BY DIRECTION")

        print("\n--- LOSSES: did the trade ever work? ---")
        print("(mfe_r = furthest it ever showed in profit, in R, before it lost)")
        per_year = defaultdict(list)
        for r in rows:
            if r["grade"] == "loss":
                per_year[r["year"]].append(r)
        for y in sorted(per_year):
            ls = per_year[y]
            dead = [r for r in ls if r["mfe_r"] < 0.1]
            gave = [r for r in ls if r["mfe_r"] >= 0.5]
            print(
                f"  {y}  losses={len(ls):3d}  never-worked(mfe<0.1R)={len(dead):3d}  "
                f"gave-back(mfe>=0.5R)={len(gave):3d}  "
                f"medianMfe={statistics.median([r['mfe_r'] for r in ls]):.2f}R"
            )

    if leg_rows:
        print("\n--- SETUPS THAT NEVER TRADED, by reason ---")
        by_year_verdict = defaultdict(lambda: defaultdict(int))
        for r in leg_rows:
            by_year_verdict[r["year"]][r["verdict"]] += 1
        verdicts = sorted({v for y in by_year_verdict.values() for v in y})
        head = "  year  " + "".join(f"{v[:22]:>24}" for v in verdicts)
        print(head)
        for y in sorted(by_year_verdict):
            print(f"  {y}  " + "".join(f"{by_year_verdict[y].get(v, 0):>24}" for v in verdicts))

    print(f"\nwrote {out}/trades.csv  and  {out}/setups.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
