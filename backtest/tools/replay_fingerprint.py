"""Fingerprint what a real replay PRODUCED, so a performance change can be proved result-identical.

🔴 **Why this exists.** Every optimisation in the replay path is worthless if it moves a number,
and "the tests pass" does not settle it: the unit tests pin behaviour on synthetic frames, and the
defects that matter here are the ones that only appear on six years of real bars — a float that
rounds differently, a bar boundary that shifts by one, a volume that becomes 0.0 instead of None.
Aaron's constraint, 2026-08-26: *"Do not sacrifice the accuracy of the back test. I want it to be
100% accurate. I just want it faster."* This is how that gets checked rather than asserted.

**Usage** — capture before the change, compare after:

    python3 backtest/tools/replay_fingerprint.py capture out.json --start 2024-01-01 --end 2026-08-23
    # ...make the change...
    python3 backtest/tools/replay_fingerprint.py compare out.json --start 2024-01-01 --end 2026-08-23

⚠ **It fingerprints the TRADES, not a summary.** Net P&L agreeing is a much weaker statement than
every entry, exit, size and reason agreeing — two different books can post the same total, and a
performance change that swapped two trades would pass a totals check silently.

⚠ **It also fingerprints the BAR STREAM itself**, which is the half a trade list cannot see: a run
that produces identical trades off a subtly different bar sequence is still a changed run, and the
next strategy through that loop would be the one to find out.

⚠ Compare only fingerprints taken on the SAME window, instrument and settings — the file records
all three and `compare` refuses when they differ, because a green comparison across two different
bases is exactly the reassurance this is meant to prevent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "command-center" / "backend"))


def _bar_stream_digest(df) -> dict:
    """A digest of exactly what `iter_bars` yields — index, timestamp, OHLC and volume.

    Built by REPLAYING the iterator rather than by hashing the frame, so it measures the thing
    under test. A change that alters how a bar is read shows up here even when no trade moves.
    """
    from backtest.replay.loop import iter_bars

    h = hashlib.sha1()
    n = 0
    first = last = None
    for bar in iter_bars(df):
        row = (
            bar.index,
            bar.timestamp_ms,
            repr(bar.time),
            repr(bar.open),
            repr(bar.high),
            repr(bar.low),
            repr(bar.close),
            repr(bar.volume),  # repr, so None and 0.0 can never look alike
        )
        h.update(str(row).encode())
        if first is None:
            first = row
        last = row
        n += 1
    return {"bars": n, "digest": h.hexdigest(), "first": first, "last": last}


def _trade_rows(strategy) -> list:
    """Every trade as a sorted list of (field, repr(value)) pairs.

    `repr` on the value, never `str`: `0.1` and `0.1000000000000001` print the same under str
    and differ under repr, and a float that rounds differently is precisely what a performance
    change can do without touching any logic.

    🔴 **The book lives on `strategy.execution.trades`, not on the strategy.** The first version
    of this file read `strategy.trades`, which does not exist — so it captured a baseline of ZERO
    trades and would have reported IDENTICAL against any change whatsoever. That is the exact
    shape of vacuous pass this repo keeps recording, in the one tool whose whole job is to stop
    a performance change moving a number. `fingerprint` now refuses a zero-trade result outright.
    """
    book = getattr(getattr(strategy, "execution", None), "trades", None)
    if book is None:
        book = getattr(strategy, "trades", None)
    out = []
    for t in book or []:
        d = t if isinstance(t, dict) else getattr(t, "__dict__", {})
        # ⚠ **LISTS, not tuples, and this is not cosmetic.** A captured fingerprint is compared
        # after a JSON round trip, and JSON has no tuple — so a freshly-built tuple never equals
        # its own reloaded self and EVERY trade reads as changed. The first version did exactly
        # that: it reported `first trade to differ: #0` and then printed no differing field,
        # because there was none. **A comparison that always says CHANGED is as useless as one
        # that always says IDENTICAL**, and it is more expensive, because it sends you looking
        # for a defect in the code under test.
        out.append(sorted([str(k), repr(v)] for k, v in d.items()))
    return out


def _strategy_digest(config) -> dict:
    """Fingerprint the STRATEGY the run used — its source and its resolved settings.

    🔴 **This exists because a comparison silently spanned a settings change and I read the
    result as a defect in my own optimisation (2026-08-26).** A baseline was captured at 20:31,
    `mpc_sos_fade.meta.json` was edited at 20:34 by somebody else working the same clone, and the
    20:41 comparison duly reported the trades had moved. They HAD moved — because the strategy
    had. The bar stream was byte-identical throughout, which is what made it so convincing.

    ⚠ **A performance change is proved by holding EVERYTHING else still, and "everything" includes
    the file somebody is editing in the next window.** This is rule 11 arriving in a tool: the
    difference column becomes the thing that lies. `compare` refuses on any of it now, so the
    honest failure is *"you changed the strategy"* rather than a false CHANGED.

    ⚠ Both halves are needed. The SOURCE catches an edit to the logic; the RESOLVED SETTINGS catch
    an edit to a default in the meta file, which changes what runs without touching a line of it.
    """
    from pathlib import Path as _P

    import config as cfg

    pkg = _P(cfg.MONOREPO_ROOT) / "strategies" / "python" / "mpc_sos_fade"
    h = hashlib.sha1()
    for f in sorted(pkg.glob("*.py")) + sorted(pkg.glob("*.json")):
        h.update(f.name.encode())
        h.update(f.read_bytes())

    settings = sorted(
        (str(k), repr(v)) for k, v in vars(config).items() if not str(k).startswith("_")
    )
    return {
        "strategy_source": h.hexdigest(),
        "strategy_settings": hashlib.sha1(str(settings).encode()).hexdigest(),
    }


def fingerprint(symbol: str, start: str, end: str, tf: str, secondary: bool, server: str) -> dict:
    from services import python_runner

    from backtest.data.source import BarSource
    from backtest.replay import build_strategy

    found = python_runner._resolve("MpcSosFadeStrategy")
    if not found:
        raise SystemExit("MpcSosFadeStrategy did not resolve")
    _pkg, entry = found

    src = BarSource(server=server)
    df = src.load(symbol, tf, start, end)
    if df.empty:
        raise SystemExit(f"no {tf} bars for {symbol} over [{start}, {end}]")

    config = python_runner._build_config(
        entry["config"], {"exec_secondary": True} if secondary else {}, symbol
    )
    strategy = build_strategy(entry["strategy"], config, initial_capital=10000.0, cost_profile=None)

    bars_fp = _bar_stream_digest(df)
    strategy_fp = _strategy_digest(config)
    if secondary:
        df2 = src.load(symbol, "M5", start, end)
        strategy.run_dual(df, df2)
    else:
        strategy.run(df)

    rows = _trade_rows(strategy)
    if not rows:
        raise SystemExit(
            f"REFUSED - the replay produced NO trades over [{start}, {end}].\n"
            "A fingerprint of an empty book compares equal to everything, so it certifies any\n"
            "change at all. Pick a window this strategy actually trades, or fix the book path."
        )
    return {
        "basis": {
            "symbol": symbol,
            "start": start,
            "end": end,
            "timeframe": tf,
            "secondary": secondary,
            "server": server,
            **strategy_fp,
        },
        "bar_stream": bars_fp,
        "trade_count": len(rows),
        "trades_digest": hashlib.sha1(str(rows).encode()).hexdigest(),
        "trades": rows,
    }


def _refuse_on_different_basis(a: dict, b: dict, allow_strategy_change: bool = False) -> None:
    """⚠ Rule 11, in miniature. A comparison across two different bases is worse than no
    comparison: it reports agreement about a question neither run was asked.

    🔴 **`--allow-strategy-change` is a DOOR, and it is here because the wall blocks the one
    comparison this tool most needs to make.** A speed change INSIDE the strategy — the bar-time
    map's prune is the first — moves the source digest, so the guard refuses and the only proof
    available is the one that cannot be run. A wall with no door gets routed around in ways that
    leave no trace, which is strictly worse; `compare_strategy.py` carries the same reasoning for
    `--allow-fast-timeframe`.

    ⚠ **It waives `strategy_source` and NOTHING ELSE.** `strategy_settings` still refuses, which
    is the half that matters most: a moved DEFAULT is a different strategy however inert the code
    change was, and waiving both would let a tuning change ride in under a performance claim. The
    window, instrument, timeframe and server still refuse too. So the flag says *I changed the
    code and assert it is inert*, never *compare these two runs however they were set up*.
    Passing it is a claim, and an unexpected CHANGED verdict underneath it is that claim being
    refuted rather than a tool malfunction.
    """
    ba, bb = dict(a.get("basis") or {}), dict(b.get("basis") or {})
    waived = None
    if allow_strategy_change:
        waived = (ba.pop("strategy_source", None), bb.pop("strategy_source", None))
    if ba != bb:
        print("REFUSED - the two fingerprints were not taken on the same basis:")
        for k in sorted(set(ba) | set(bb)):
            if ba.get(k) != bb.get(k):
                print(f"  {k}: {ba.get(k)!r} vs {bb.get(k)!r}")
        raise SystemExit(2)
    if waived is not None and waived[0] != waived[1]:
        print(
            "NOTE - the strategy source CHANGED and the refusal was waived by --allow-strategy-change."
        )
        print("       Everything below is a claim that the change was inert. Read it as one.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["capture", "compare"])
    ap.add_argument("path")
    ap.add_argument("--symbol", default="XAUUSD.p")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--timeframe", default="M15")
    ap.add_argument("--secondary", action="store_true")
    ap.add_argument("--server", default="PUPrime-Demo")
    ap.add_argument(
        "--allow-strategy-change",
        action="store_true",
        help="compare across a change to the strategy's own SOURCE (a perf change inside it). "
        "Waives strategy_source only - a moved default still refuses.",
    )
    a = ap.parse_args()

    fp = fingerprint(a.symbol, a.start, a.end, a.timeframe, a.secondary, a.server)

    if a.action == "capture":
        Path(a.path).write_text(json.dumps(fp, indent=1, sort_keys=True))
        print(
            f"captured {fp['trade_count']} trades over {fp['bar_stream']['bars']:,} bars\n"
            f"  bars   {fp['bar_stream']['digest']}\n"
            f"  trades {fp['trades_digest']}\n"
            f"-> {a.path}"
        )
        return

    old = json.loads(Path(a.path).read_text())
    _refuse_on_different_basis(old, fp, allow_strategy_change=a.allow_strategy_change)

    bars_ok = old["bar_stream"]["digest"] == fp["bar_stream"]["digest"]
    trades_ok = old["trades_digest"] == fp["trades_digest"]

    print(
        f"bars   : {old['bar_stream']['bars']:,} -> {fp['bar_stream']['bars']:,}  "
        f"{'IDENTICAL' if bars_ok else 'CHANGED'}"
    )
    print(
        f"trades : {old['trade_count']} -> {fp['trade_count']}  "
        f"{'IDENTICAL' if trades_ok else 'CHANGED'}"
    )

    if not bars_ok:
        print(f"  first bar was {old['bar_stream']['first']}")
        print(f"  first bar now {fp['bar_stream']['first']}")
        print(f"  last  bar was {old['bar_stream']['last']}")
        print(f"  last  bar now {fp['bar_stream']['last']}")

    if not trades_ok:
        # Name the FIRST divergence: after one trade moves every later one is downstream of it,
        # so a full diff buries the one line worth reading. Both sides are lists (see
        # `_trade_rows`), so this compares like with like.
        for i, (o, n) in enumerate(zip(old["trades"], fp["trades"])):
            if o != n:
                print(f"  first trade to differ: #{i}")
                for (ko, vo), (_kn, vn) in zip(o, n):
                    if vo != vn:
                        print(f"    {ko}: {vo} -> {vn}")
                break
        else:
            print("  the books agree as far as they overlap; the LENGTH differs")

    raise SystemExit(0 if (bars_ok and trades_ok) else 1)


if __name__ == "__main__":
    main()
