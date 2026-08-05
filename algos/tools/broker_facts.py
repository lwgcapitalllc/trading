"""broker_facts.py — MEASURE a live broker's costs instead of assuming them.

    python algos/tools/broker_facts.py --bot mpc_sos_fade_demo
    python algos/tools/broker_facts.py --bot mpc_sos_fade_demo --sample 300

**Why this exists.** G5 in `docs/LIVE_TRADING_PIPELINE.md`: *the broker and symbol are not the
backtest broker*. Every cost figure in this repo was measured on **VANTAGE** and the live bot
trades **PU PRIME**, and the two are not interchangeable — this repo has already recorded a 50%
error from quoting one broker's spread for the other ($0.22 vs $0.33 on XAUUSD), and the
2026-08-04 shadow diff found the two feeds differ by a systematic 4-5 cents on every bar.

It is **READ-ONLY** and places nothing. It attaches to a terminal that is already running and
logged in, reads the symbol specification, then samples live ticks to build a spread
DISTRIBUTION.

⚠ **A single spread reading is not the spread.** `symbol_info().spread` is one instant, and the
instance config's `_measured` block records exactly that — "spread 33 points" taken once on
2026-07-31. Gold's spread widens at the rollover, around news and out of hours; the Vantage figure
this repo trusts is a MEDIAN over 1.49M ticks. So the sampler is the point of this tool and the
specification read is the cheap half.

⚠ **It asserts the ACCOUNT before reporting anything.** `mt5.initialize()` with no path attaches
to whatever terminal is open, and this box runs two — MT5_FFT (PU Prime, the live bot) and MT5_Lab
(Vantage, the backtest agent). Reporting Vantage's swap as PU Prime's is precisely the error the
tool exists to end, and it would look completely normal. The path comes from the bot's own instance
config and the account number is checked against it.

⚠ **It does not write anything.** The numbers are printed for a human to paste into the instance
config's `_measured` block, because that block is a claim about when a measurement was taken and by
whom, and a tool silently rewriting it would make it impossible to tell a fresh reading from a
stale one.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
INSTANCES = REPO / "algos" / "markets" / "fx" / "instances"

# This runs on the VPS, where the console is cp1252 and a single non-ASCII character raises
# UnicodeEncodeError mid-print. It cost this tool its whole run on the first try: every number was
# measured and printed, then a trailing warning line killed the process with a traceback and an
# exit code 1, so a SUCCESSFUL measurement looked like a crash. The printed strings are ASCII now,
# and this is the belt for the next person who forgets — `errors="replace"` degrades one character
# rather than discarding the report it was decorating.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


def load_instance(bot_key: str) -> dict:
    cfg = INSTANCES / bot_key / "config.json"
    if not cfg.exists():
        raise SystemExit(f"no instance config at {cfg}")
    return json.loads(cfg.read_text(encoding="utf-8"))


def attach(mt5, path: str, want_account: int) -> None:
    """Attach to an ALREADY-RUNNING terminal and refuse if it is not the right account.

    No login is attempted: the bot owns that, and re-logging in a terminal a live bot is trading
    through is not a read-only act. If the terminal is not up, this fails rather than starting one.
    """
    if not mt5.initialize(path=path):
        raise SystemExit(f"could not attach to {path}: {mt5.last_error()}")
    info = mt5.account_info()
    if info is None:
        mt5.shutdown()
        raise SystemExit("attached, but the terminal reports no account — is it logged in?")
    if int(info.login) != int(want_account):
        got, srv = info.login, info.server
        mt5.shutdown()
        raise SystemExit(
            f"WRONG TERMINAL: attached to account {got} on {srv}, expected {want_account}. "
            f"Refusing to report one broker's costs as another's.")


def spec(mt5, symbol: str) -> dict:
    s = mt5.symbol_info(symbol)
    if s is None:
        raise SystemExit(f"symbol {symbol} not found on this terminal")
    return {
        "symbol": s.name,
        "digits": s.digits,
        "point": s.point,
        "contract_size": s.trade_contract_size,
        "tick_value": s.trade_tick_value,
        "tick_size": s.trade_tick_size,
        "volume_min": s.volume_min,
        "volume_max": s.volume_max,
        "volume_step": s.volume_step,
        # The broker's OWN minimum stop distance, in points. Independent of our own
        # `exec_min_stop_mode` guard and enforced at the terminal — see the note printed below.
        "stops_level_points": s.trade_stops_level,
        "freeze_level_points": s.trade_freeze_level,
        # Signed, and the sign is load-bearing: gold's SHORT swap is normally a CREDIT.
        "swap_long": s.swap_long,
        "swap_short": s.swap_short,
        "swap_mode": s.swap_mode,
        "swap_rollover_3days": s.swap_rollover3days,
        "spread_now_points": s.spread,
        "spread_float": s.spread_float,
    }


def sample_spread(mt5, symbol: str, seconds: int, point: float) -> dict:
    """Sample the live bid/ask gap once a second and report the DISTRIBUTION.

    Returns `None` for the stats when the market is shut — a stale tick repeated for five minutes
    would otherwise be reported as a rock-steady spread, which is the most confident-looking wrong
    answer this tool could give.
    """
    seen: list[float] = []
    stale = 0
    last_ms = None
    end = time.time() + seconds
    while time.time() < end:
        t = mt5.symbol_info_tick(symbol)
        if t is None:
            time.sleep(1.0)
            continue
        if last_ms is not None and t.time_msc == last_ms:
            stale += 1
        else:
            seen.append(float(t.ask) - float(t.bid))
        last_ms = t.time_msc
        time.sleep(1.0)

    if not seen:
        return {"n": 0, "stale_reads": stale, "note": "no fresh ticks - market shut?"}

    seen.sort()
    def pct(p: float) -> float:
        return seen[min(len(seen) - 1, int(p / 100 * len(seen)))]

    return {
        "n": len(seen),
        "stale_reads": stale,
        "min": seen[0],
        "median": statistics.median(seen),
        "p90": pct(90),
        "p99": pct(99),
        "max": seen[-1],
        "median_points": statistics.median(seen) / point if point else None,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Measure a live broker's symbol costs. Read-only.")
    ap.add_argument("--bot", required=True)
    ap.add_argument("--sample", type=int, default=120,
                    help="seconds of live ticks to sample for the spread distribution (0 = skip)")
    args = ap.parse_args(argv)

    inst = load_instance(args.bot)
    symbol = inst["symbol"]

    import MetaTrader5 as mt5
    attach(mt5, inst["mt5_path"], inst["account"])
    try:
        acct = mt5.account_info()
        print(f"broker_facts {args.bot}")
        print(f"  terminal   {inst['mt5_path']}")
        print(f"  account    {acct.login} / {acct.server} / {acct.currency} "
              f"/ balance {acct.balance:,.2f}")
        print()

        s = spec(mt5, symbol)
        print(f"SPECIFICATION - {s['symbol']}")
        for k in ("digits", "point", "contract_size", "tick_value", "tick_size",
                  "volume_min", "volume_max", "volume_step",
                  "stops_level_points", "freeze_level_points",
                  "swap_long", "swap_short", "swap_mode", "swap_rollover_3days",
                  "spread_now_points", "spread_float"):
            print(f"  {k:<22} {s[k]}")

        pt = float(s["point"] or 0.01)
        print()
        print("READ THESE TWO CAREFULLY")
        print(f"  broker minimum stop  {s['stops_level_points']} points "
              f"= ${s['stops_level_points'] * pt:.2f} - enforced by the TERMINAL, independent of "
              f"exec_min_stop_mode")
        print(f"  swap long / short    {s['swap_long']} / {s['swap_short']} - a POSITIVE value is "
              f"a credit paid TO you, and gold's short swap normally is one")

        if args.sample > 0:
            print()
            print(f"SAMPLING the spread for {args.sample}s ...", flush=True)
            d = sample_spread(mt5, symbol, args.sample, pt)
            if not d.get("n"):
                print(f"  {d.get('note')} ({d['stale_reads']} repeated ticks)")
            else:
                print(f"  {d['n']} fresh reads ({d['stale_reads']} repeats)")
                print(f"  min ${d['min']:.2f} | median ${d['median']:.2f} "
                      f"({d['median_points']:.0f} points) | p90 ${d['p90']:.2f} "
                      f"| p99 ${d['p99']:.2f} | max ${d['max']:.2f}")
                print()
                print("  NOTE: a few minutes is a SNAPSHOT of one session, not the spread. Gold")
                print("  widens at the 17:00 NY rollover, around news and out of hours. Sample")
                print("  again in another session before quoting a median as the broker's cost.")
    finally:
        mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
