#!/usr/bin/env python3
"""trade_export.py — replay ANY strategy in the registry and write its finished trades.

WHY THIS EXISTS. `tools/run_report.py` is the rich report, and it is SOS-Fade-shaped: it reads
a per-bar decision log and a setup population to answer "which setups never traded, and why".
That is worth having and it is not universal. The extreme leg keeps no decision log, so the
only way to get its trade list out was to bend the report tool into a shape it is not, on a
two-hour replay, to produce two columns.

This tool produces exactly those two columns and nothing else: **when the trade was entered,
and what it made in R**. That is the whole input a conditioning study needs — see
`backtest/regime_study/` and `backtest/notes/regime-grading.md` — and it is the same input for
every strategy, present and future, so this stays strategy-agnostic by construction.

⚠ **It is a REPLAY, not a report.** No costs are charged (no cost profile is passed), so the R
figures are the zero-cost Pine-equivalent ones. A study that conditions on market state is
comparing trades against EACH OTHER, and costs shift every bucket by roughly the same amount,
so this is the honest tool for that job and the wrong one for quoting an absolute return.

⚠ **Finished trades only.** A position still open at the last bar is not written, because its R
is not known yet and a zero there would be indistinguishable from a scratch (root rule 1).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd  # noqa: E402

from backtest.data.source import BarSource  # noqa: E402
from backtest.replay.build import build_strategy  # noqa: E402
from backtest.replay.registry import STRATEGIES, load  # noqa: E402

__all__ = ["finished_trades", "main"]


def _entry_time(trade, df) -> pd.Timestamp | None:
    """The trade's entry timestamp, from whichever field the strategy filled in.

    Strategies do not agree: some stamp an epoch in milliseconds, some keep only the bar
    INDEX into the frame they were replayed on. Both are resolved here rather than in each
    caller. Returns None — never a fabricated time — when neither is present, so a trade with
    no usable stamp is dropped loudly instead of landing on bar zero.
    """
    ms = getattr(trade, "entry_ms", None)
    if ms is not None:
        return pd.to_datetime(int(ms), unit="ms")
    idx = getattr(trade, "entry_index", None)
    if idx is not None and 0 <= int(idx) < len(df):
        return df.index[int(idx)]
    return None


def finished_trades(strat, df) -> list[dict]:
    """Every closed trade the replayed strategy holds, as {entry_utc, r, dir, exit_reason}."""
    book = getattr(strat, "execution", strat)
    trades = getattr(book, "trades", None)
    if trades is None:
        raise AttributeError(
            f"{type(strat).__name__} exposes no trade list. Every strategy's execution layer "
            f"keeps one; if this one names it differently, name it here rather than teaching "
            f"each caller a second place to look."
        )
    rows = []
    for t in trades:
        when = _entry_time(t, df)
        if when is None:
            continue
        rows.append(
            {
                "entry_utc": when.isoformat(),
                "r": getattr(t, "r", None),
                "dir": getattr(t, "dir", None),
                "exit_reason": getattr(t, "exit_reason", None),
            }
        )
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", required=True, choices=sorted(STRATEGIES))
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="5", help="replay timeframe in minutes")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        metavar="FIELD=VALUE",
        help="override a config field. Repeatable. A field the config does not declare "
        "RAISES — silently running the default would make the run a lie about itself.",
    )
    ap.add_argument("--out", required=True, help="CSV path to write")
    args = ap.parse_args(argv)

    spec = load(args.strategy)
    StrategyCls, ConfigCls = spec["strategy"], spec["config"]

    print(f"loading {args.symbol} {args.tf}m  {args.start} -> {args.end} ...", flush=True)
    df = BarSource().load(args.symbol, args.tf, args.start, args.end)
    if df.empty:
        print("no bars returned — is the MT5 agent tunnel up?")
        return 1
    print(f"  {len(df):,} bars  {df.index[0]} -> {df.index[-1]}", flush=True)

    import dataclasses

    fields = {f.name for f in dataclasses.fields(ConfigCls)}
    kwargs = {"symbol": args.symbol} if "symbol" in fields else {}
    cfg = ConfigCls(**kwargs)
    for ov in args.overrides:
        if "=" not in ov:
            raise SystemExit(f"--set expects FIELD=VALUE, got {ov!r}")
        field, raw = ov.split("=", 1)
        field = field.strip()
        if not hasattr(cfg, field):
            raise SystemExit(f"--set {field!r}: no such field on {ConfigCls.__name__}")
        cur = getattr(cfg, field)
        if isinstance(cur, bool):
            val: object = raw.strip().lower() in ("1", "true", "yes", "on")
        elif isinstance(cur, int):
            val = int(raw)
        elif isinstance(cur, float):
            val = float(raw)
        else:
            val = raw
        cfg = dataclasses.replace(cfg, **{field: val})
        print(f"  override {field} = {val} (was {cur})", flush=True)

    strat = build_strategy(StrategyCls, cfg, initial_capital=args.capital)
    print(f"replaying {args.strategy} (warmup {args.warmup}) ...", flush=True)
    strat.run(df, warmup=args.warmup)

    rows = finished_trades(strat, df)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["entry_utc", "r", "dir", "exit_reason"])
        w.writeheader()
        w.writerows(rows)
    total = sum(r["r"] for r in rows if r["r"] is not None)
    print(f"  {len(rows)} trades, sumR = {total:.1f}  ->  {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
