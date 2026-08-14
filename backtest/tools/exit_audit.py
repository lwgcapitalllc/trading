#!/usr/bin/env python3
"""exit_audit.py — HOW do trades die, and how much was on the table when they did?

The lab reports what a run MADE. `run_report.py` reports what market it made it in. Neither
answers the question a runner-based strategy actually raises, which is Aaron's (2026-08-08):

    "what percentage of my trades are just coming back to entry, and is there a way to
     maximize on some of these?"

A trade that scratches is invisible in every summary this repo produces. It is not a loss, so
it does not appear in the loss column; it is (barely) a win, so it inflates the win rate while
contributing nothing. **The only way to see it is to ask each trade how far it ran BEFORE it
came back**, and that is what this tool does.

**The ladder is the frame, because on this strategy the ladder decides the outcome.** At the
shipped defaults `exec_tp1_pct` and `exec_tp2_pct` are BOTH 0, so TP1 and TP2 bank nothing —
they only stage the stop:

    stage 0   never reached TP1   stop is the initial stop        -> a full -1R loss
    stage 1   reached TP1         stop moves to entry +/- buffer  -> a scratch if price returns
    stage 2   reached TP2         stop floor becomes the TP1 price -> a real profit if it returns

So a "breakeven" trade is not any trade that drifted back to entry. **It is precisely a trade
that reached TP1 and not TP2**, and every one of them is a trade the strategy was right about
far enough to move its stop. That is what makes the group worth measuring rather than writing
off: they are the setups that WORKED and were not converted.

⚠ **`reached TP1` is derived from the trade's own frozen ladder** (`Trade.tp1`/`tp2`, copied at
placement) against `Trade.mfe_price`, the best price the hold ever saw. It is NOT re-derived from
fib anchors here — that would be a second claim about a leg the trade cannot re-run, the same
rule `output.py::_trade_fib` states. It is also why stage cannot simply be read back: the
strategy clears it when the trade closes.

⚠ **Excursion is measured on bar high/low, so it is the same intrabar approximation the trail
itself uses.** A trade whose MFE reads +1.4R touched that price on some bar; it does not mean the
price was available to a resting order for any length of time. Read the MFE column as *how far
the move went*, never as *what a target would have filled*.

⚠ **`exec_secondary` is PINNED OFF and this is a single-stream replay.** The 1-minute re-entry
needs `run_dual` and a second bar frame; replaying single-stream with it on would silently return
a primary-only book, which is this repo's most-repeated defect. It is 8 trades in 7.9 years and
none of them are A+ primaries, so the answer here is about the primary book either way — but say
so rather than letting the default decide quietly.

Usage:
    python backtest/tools/exit_audit.py --start 2020-01-01 --end 2026-08-06
"""

from __future__ import annotations

import argparse
import dataclasses
import statistics
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_STRATEGIES = {
    "mpc_sos_fade": "strategies.python.mpc_sos_fade",
    "mpc_bleg": "strategies.python.mpc_bleg",
}


def _touched(trade, target: float) -> bool:
    """Did the hold's best price ever reach this rung?

    `mfe_price` is the deepest FAVOURABLE price, so the comparison flips with direction. A rung
    of 0.0 means the trade never froze one and is reported as untouched rather than as reached —
    an unset target must not read as a target that was hit.
    """
    if not target:
        return False
    return trade.mfe_price >= target if trade.dir > 0 else trade.mfe_price <= target


def _pct(n: int, total: int) -> str:
    return f"{(100.0 * n / total):5.1f}%" if total else "    -"


def _describe(label: str, rows: list, total: int) -> str:
    if not rows:
        return f"  {label:<34} {0:>4}  {_pct(0, total)}"
    rs = [r["r"] for r in rows]
    return (
        f"  {label:<34} {len(rows):>4}  {_pct(len(rows), total)}"
        f"   R sum {sum(rs):>8.2f}   median {statistics.median(rs):>6.3f}"
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="How trades die, and what was on the table.")
    ap.add_argument("--strategy", default="mpc_sos_fade", choices=sorted(_STRATEGIES))
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (default: today)")
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
        print("no bars returned — is the MT5 agent tunnel up on localhost:8766?")
        return 1
    print(f"  {len(df):,} bars  {df.index[0]} -> {df.index[-1]}", flush=True)

    cfg = ConfigCls(fill_model="bar", symbol=args.symbol)
    patch: dict = {}
    if hasattr(cfg, "exec_secondary"):
        patch["exec_secondary"] = False  # see the module docstring
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
    band = getattr(cfg, "exec_scratch_r", 0.15)

    rows = []
    for t in trades:
        risk = t.risk_usd or 1.0
        rows.append(
            {
                "dir": "long" if t.dir > 0 else "short",
                "r": t.r,
                "mfe_r": t.mfe_usd / risk,
                "tp1": _touched(t, t.tp1),
                "tp2": _touched(t, t.tp2),
                "hours": (t.exit_ms - t.entry_ms) / 3_600_000.0 if t.exit_ms else 0.0,
                "reason": t.exit_reason,
            }
        )
    n = len(rows)
    if not n:
        print("no trades in this window")
        return 1

    wins = [r for r in rows if r["r"] > band]
    scratches = [r for r in rows if -band <= r["r"] <= band]
    losses = [r for r in rows if r["r"] < -band]

    print("\n" + "=" * 96)
    print(
        f"{args.strategy}  {args.symbol} {args.tf}m   {df.index[0].date()} -> {df.index[-1].date()}"
        f"   {n} trades   scratch band +/-{band}R"
    )
    print(
        f"  TP1 size {cfg.exec_tp1_pct}%  TP2 size {cfg.exec_tp2_pct}%  "
        f"BE buffer {cfg.exec_be_buf_tk} ticks  trail {cfg.exec_runner_trail!r}"
    )
    print("=" * 96)

    # Peak-to-trough on the CLOSED-TRADE cumulative R curve. Reported beside total R because on
    # this strategy they move in opposite directions under every exit-side lever measured so far:
    # a looser stop buys R and pays for it in drawdown, and quoting either alone picks the answer.
    # ⚠ It is a trade-sequence drawdown, not the intrabar one — the real trough is deeper, since a
    # trade open through the worst stretch is not marked to market here. Use it to COMPARE rows,
    # never as the account's true worst moment.
    cum = peak = 0.0
    max_dd = 0.0
    for r in rows:
        cum += r["r"]
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    print(
        f"\nOUTCOME MIX          (total R {sum(r['r'] for r in rows):.2f}"
        f"   maxDD {max_dd:.2f}R   R per trade {sum(r['r'] for r in rows) / n:+.3f})"
    )
    print(_describe("WON  (> +%.2fR)" % band, wins, n))
    print(_describe("SCRATCHED (came back to BE)", scratches, n))
    print(_describe("LOST (< -%.2fR)" % band, losses, n))

    print("\nHOW FAR UP THE LADDER EACH GROUP GOT")
    print(f"  {'group':<28}{'n':>5}{'reached TP1':>14}{'reached TP2':>14}")
    for label, grp in (("won", wins), ("scratched", scratches), ("lost", losses)):
        t1 = sum(1 for r in grp if r["tp1"])
        t2 = sum(1 for r in grp if r["tp2"])
        print(f"  {label:<28}{len(grp):>5}{t1:>8} {_pct(t1, len(grp))}{t2:>8} {_pct(t2, len(grp))}")

    print("\nTHE SCRATCHES — HOW MUCH WAS ON THE TABLE BEFORE THEY CAME BACK")
    if scratches:
        mfes = sorted(r["mfe_r"] for r in scratches)
        print(
            f"  peak unrealised R:  median {statistics.median(mfes):.2f}R   "
            f"mean {statistics.mean(mfes):.2f}R   max {mfes[-1]:.2f}R   min {mfes[0]:.2f}R"
        )
        for thr in (0.5, 1.0, 1.5, 2.0, 3.0):
            over = [m for m in mfes if m >= thr]
            print(
                f"    ran to >= {thr:>3.1f}R at some point:  {len(over):>3}"
                f"  ({_pct(len(over), len(scratches)).strip()} of scratches,"
                f" {_pct(len(over), n).strip()} of all trades)"
                f"   total unrealised {sum(over):>7.2f}R"
            )
        print(f"  hold time:  median {statistics.median([r['hours'] for r in scratches]):.1f}h")
        by_dir = {}
        for r in scratches:
            by_dir.setdefault(r["dir"], []).append(r)
        for d, grp in sorted(by_dir.items()):
            print(
                f"  {d:<6} {len(grp):>3}  median peak {statistics.median([x['mfe_r'] for x in grp]):.2f}R"
            )

    print("\nWHAT THE WINNERS GAVE BACK (for scale — the cost side of any change)")
    if wins:
        give = [r["mfe_r"] - r["r"] for r in wins]
        print(
            f"  median peak {statistics.median([r['mfe_r'] for r in wins]):.2f}R   "
            f"median booked {statistics.median([r['r'] for r in wins]):.2f}R   "
            f"median given back {statistics.median(give):.2f}R"
        )
        big = [r for r in wins if r["r"] >= 3.0]
        print(
            f"  winners >= 3R: {len(big)}  ({_pct(len(big), n).strip()} of all trades), "
            f"carrying {sum(r['r'] for r in big):.2f}R of the book's {sum(r['r'] for r in rows):.2f}R"
        )

    print("\nEXIT REASONS")
    reasons: dict = {}
    for r in rows:
        reasons.setdefault(r["reason"] or "(none)", []).append(r["r"])
    for reason, rs in sorted(reasons.items(), key=lambda kv: -len(kv[1])):
        print(f"  {reason:<20} {len(rs):>4}  {_pct(len(rs), n)}   R sum {sum(rs):>8.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
