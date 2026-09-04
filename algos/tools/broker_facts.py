"""broker_facts.py — MEASURE a live broker's costs instead of assuming them.

    python algos/tools/broker_facts.py --bot sos_fade_demo
    python algos/tools/broker_facts.py --bot sos_fade_demo --sample 300

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
            f"Refusing to report one broker's costs as another's."
        )


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

    ⚠ **The symbol is SELECTED into Market Watch first, and that is not a nicety.** MT5 streams
    ticks only for symbols the terminal is watching, and `symbol_info_tick` on an unwatched symbol
    returns `None` — forever, in a perfectly healthy session. This tool read that as "market shut?"
    on 2026-08-12, five minutes into a live London/NY overlap, because the account had just been
    switched to a tier whose symbol (`XAUUSD.p`) was not in the new account's Market Watch.
    `symbol_select` writes nothing and changes no order state; the read alone is what was missing.

    ⚠ **A tick that never ARRIVED and a tick that never MOVED are counted separately**, because
    they are different failures wearing one sentence: `none_reads` means the terminal would not
    answer (unwatched symbol, dead link), `stale_reads` means it answered with the same tick
    (genuinely shut market). Collapsing them is this repo's own no-vs-cannot-ask rule, and the
    version that did sent the reader at the market instead of at the terminal.
    """
    seen: list[float] = []
    stale = 0
    none_reads = 0
    last_ms = None
    # Market Watch only — no order state, no chart, nothing persisted about trading.
    selected = bool(mt5.symbol_select(symbol, True))
    end = time.time() + seconds
    while time.time() < end:
        t = mt5.symbol_info_tick(symbol)
        if t is None:
            none_reads += 1
            time.sleep(1.0)
            continue
        if last_ms is not None and t.time_msc == last_ms:
            stale += 1
        else:
            seen.append(float(t.ask) - float(t.bid))
        last_ms = t.time_msc
        time.sleep(1.0)

    if not seen:
        if none_reads and not stale:
            note = (
                "the terminal returned NO tick at all - the symbol is not streaming. "
                f"symbol_select({symbol}) returned {selected}; check it is in Market Watch "
                "and that this account quotes it. This is NOT a shut market."
            )
        else:
            note = "no fresh ticks - market shut?"
        return {
            "n": 0,
            "stale_reads": stale,
            "none_reads": none_reads,
            "selected": selected,
            "note": note,
        }

    seen.sort()

    def pct(p: float) -> float:
        return seen[min(len(seen) - 1, int(p / 100 * len(seen)))]

    return {
        "n": len(seen),
        "stale_reads": stale,
        "none_reads": none_reads,
        "selected": selected,
        "min": seen[0],
        "median": statistics.median(seen),
        "p90": pct(90),
        "p99": pct(99),
        "max": seen[-1],
        "median_points": statistics.median(seen) / point if point else None,
    }


def _pct(sorted_vals: list, p: float) -> float:
    return sorted_vals[min(len(sorted_vals) - 1, int(p / 100 * len(sorted_vals)))]


def history_spread(mt5, symbol: str, days: int, point: float) -> dict:
    """The spread distribution over the terminal's own STORED ticks, bucketed by UTC hour.

    ⚠ THIS IS THE MEASUREMENT `--sample` CANNOT MAKE, AND THE REASON IT EXISTS. Live sampling can
    only ever see the session you happen to be sitting in — the first PU Prime reading (2026-08-05)
    was 120 seconds of the London/NY overlap, and its own note said to re-run in an Asian session
    and across a rollover before the number went into a cost model. You cannot do that by waiting;
    you do it by reading the ticks the terminal already holds. Gold prints ~630k ticks a day here,
    so three days is a bigger sample than the 1.49M-tick Vantage figure this repo trusts.

    ⚠ THE TICK CLOCK IS THE BROKER'S, NOT UTC, AND THE OFFSET IS MEASURED RATHER THAN READ FROM
    CONFIG. `algos/CLAUDE.md` records that MT5 labels broker-server seconds as though they were
    UTC — the bug that put every bar 2-3 hours out behind a perfectly valid timestamp. The instance
    config carries `broker_tz_offsets 2,3`, but that is a CLAIM about summer and winter, and only
    one of them is true today. Bucketing by an assumed offset would put the Asian session's spread
    under the London label and read as a completely ordinary result. So the newest tick is compared
    against this machine's own UTC clock and the offset is rounded to the hour.

    ⚠ Ticks are pulled a DAY AT A TIME. One call for the whole window returns a single array of
    several million rows; the chunking keeps the peak allocation to roughly one day and lets a
    partial history still report (a broker's tick store starts somewhere, exactly like its bars).
    """
    import datetime as dt

    now = dt.datetime.utcnow()
    now_epoch = dt.datetime.now(dt.timezone.utc).timestamp()

    # Measure the server clock off the LIVE tick, before touching history.
    # 🔴 The first version of this took it from the first history chunk it happened to process,
    # which is the OLDEST one — so it measured "two days ago minus now" and reported UTC-48. The
    # overall distribution was unharmed (it needs no clock at all), but every by-hour label was
    # silently the BROKER's hour wearing a UTC heading, which is this repo's own never-assume-the-
    # clock trap reintroduced by the very code written to avoid it. -48 also happens to be ≡ 0
    # (mod 24), so the buckets looked like a plausible, self-consistent, wrong answer.
    live = mt5.symbol_info_tick(symbol)
    offset_h = round((int(live.time) - now_epoch) / 3600.0) if live is not None else None

    spreads: list[float] = []
    by_hour: dict[int, list[float]] = {}
    days_seen = 0

    for d in range(days, 0, -1):
        lo = now - dt.timedelta(days=d)
        hi = now - dt.timedelta(days=d - 1)
        ticks = mt5.copy_ticks_range(symbol, lo, hi, mt5.COPY_TICKS_INFO)
        if ticks is None or len(ticks) == 0:
            continue
        days_seen += 1
        for t in ticks:
            bid, ask = float(t[1]), float(t[2])
            if bid <= 0.0 or ask <= 0.0:
                continue  # a half-populated tick is not a spread
            s = ask - bid
            if s < 0:
                continue  # crossed book — never a cost, always a data artefact
            spreads.append(s)
            if offset_h is not None:
                # `None` = the live tick could not be read, so the offset is UNKNOWN. Bucketing
                # anyway would publish broker hours under a UTC heading; the overall distribution
                # below needs no clock and is still reported.
                utc_h = (dt.datetime.utcfromtimestamp(int(t[0])).hour - offset_h) % 24
                by_hour.setdefault(utc_h, []).append(s)

    if not spreads:
        return {"n": 0, "note": "the terminal holds no ticks for this window"}

    spreads.sort()
    out = {
        "n": len(spreads),
        "days": days_seen,
        "server_offset_h": offset_h,
        "min": spreads[0],
        "median": statistics.median(spreads),
        "p90": _pct(spreads, 90),
        "p99": _pct(spreads, 99),
        "max": spreads[-1],
        "median_points": statistics.median(spreads) / point if point else None,
        "by_hour": {},
    }
    for h in sorted(by_hour):
        v = sorted(by_hour[h])
        out["by_hour"][h] = {"n": len(v), "median": statistics.median(v), "p99": _pct(v, 99)}
    return out


_TRADE_MODE = {0: "DISABLED", 1: "LONG ONLY", 2: "SHORT ONLY", 3: "CLOSE ONLY", 4: "FULL"}


def sibling_symbols(mt5, symbol: str) -> list:
    """Every symbol on this terminal sharing this one's ROOT — i.e. the same market, quoted again.

    **Why this exists, and it is not curiosity.** `backtest/fills.py` used to give every PU Prime
    account tier one swap, on the reasoning that overnight financing is a fact about the SYMBOL and
    therefore the same across a broker's tiers. Nobody could check it, so it survived as an
    assumption for weeks.

    🔴 **Running this is what disproved it.** On the live PU Prime demo, `XAUUSD.s` and
    `XAUUSD.crp` are the SAME market (median M15 close difference $0.08 over 200 shared bars) on
    ONE account, and carry swaps 8.5x apart — long -79.60 vs -9.35 — with the short CREDIT gone
    entirely, +30.25 vs +0.04. A strategy trading both sides has its whole swap arithmetic decided
    by that credit.

    ⚠ **Read `trade_mode` before drawing any conclusion.** `XAUUSD.crp` looks like a far cheaper
    product and is `DISABLED` on this account, so it is evidence rather than an opportunity — which
    is exactly the mistake this column exists to stop somebody making.
    """
    root = symbol.split(".", 1)[0].upper()
    out = []
    for s in mt5.symbols_get() or []:
        if s.name.split(".", 1)[0].upper() != root:
            continue
        mt5.symbol_select(s.name, True)  # market watch only — changes no order state
        f = mt5.symbol_info(s.name) or s
        tick = mt5.symbol_info_tick(s.name)
        out.append(
            {
                "symbol": f.name,
                "path": f.path,
                "trade_mode": _TRADE_MODE.get(f.trade_mode, f.trade_mode),
                "contract_size": f.trade_contract_size,
                "digits": f.digits,
                "swap_long": f.swap_long,
                "swap_short": f.swap_short,
                "spread_points": f.spread,
                "live_spread": (
                    round(tick.ask - tick.bid, 5) if tick and tick.ask and tick.bid else None
                ),
            }
        )
    return sorted(out, key=lambda r: r["symbol"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Measure a live broker's symbol costs. Read-only.")
    # Two ways to say WHICH terminal and account. `--bot` reads them out of a registered bot's
    # instance config and is the everyday path. `--path/--account/--symbol` names them directly,
    # for an account that is not a bot — which is the only way to measure a second ACCOUNT TIER,
    # the open question in `docs/BROKER_QUESTIONS.md`. Both routes go through the same `attach()`,
    # so the account assertion is NOT weakened: an explicit run still has to state the account it
    # expects and still refuses a terminal logged into a different one. That check is the whole
    # reason this tool can be trusted — reporting one tier's costs as another's is the error it
    # exists to end, and it would look completely normal.
    ap.add_argument(
        "--bot",
        help="a registered bot key; reads terminal, account and symbol from its instance config",
    )
    ap.add_argument(
        "--path",
        help="terminal64.exe of an ALREADY-RUNNING, already-logged-in "
        "terminal (use with --account and --symbol)",
    )
    ap.add_argument(
        "--account",
        type=int,
        help="the account number you EXPECT to be logged in. Refuses on mismatch.",
    )
    ap.add_argument(
        "--symbol",
        help="symbol to read. Required with --path, and worth passing even "
        "with --bot: PU Prime suffixes the tier onto the name, so the "
        "same market is XAUUSD.s on Standard and XAUUSD.p on a raw "
        "tier. --symbols lists what this account actually carries.",
    )
    ap.add_argument(
        "--symbols",
        action="store_true",
        help="ALSO list every symbol on this terminal sharing this one's root, with "
        "its trade mode, swap and spread. This is how you check whether a cost "
        "you are about to assume is shared actually is — see sibling_symbols().",
    )
    ap.add_argument(
        "--sample",
        type=int,
        default=120,
        help="seconds of live ticks to sample for the spread distribution (0 = skip)",
    )
    ap.add_argument(
        "--history-days",
        type=int,
        default=0,
        help="ALSO read the terminal's stored ticks over the last N days and report the "
        "spread by UTC hour. This is the only way to see the Asian session and the "
        "rollover without waiting for them.",
    )
    args = ap.parse_args(argv)

    if args.bot:
        inst = load_instance(args.bot)
        path, account = inst["mt5_path"], inst["account"]
        symbol = args.symbol or inst["symbol"]
        label = args.bot
    else:
        # No partial credit: a path with no account would attach to whatever is open and report it
        # without checking, which is precisely the failure `attach()` exists to prevent.
        missing = [
            f
            for f, v in (
                ("--path", args.path),
                ("--account", args.account),
                ("--symbol", args.symbol),
            )
            if not v
        ]
        if missing:
            ap.error(
                f"either --bot, or all of --path/--account/--symbol (missing: {', '.join(missing)})"
            )
        path, account, symbol = args.path, args.account, args.symbol
        label = f"account {account}"

    import MetaTrader5 as mt5

    attach(mt5, path, account)
    try:
        acct = mt5.account_info()
        print(f"broker_facts {label}")
        print(f"  terminal   {path}")
        print(
            f"  account    {acct.login} / {acct.server} / {acct.currency} "
            f"/ balance {acct.balance:,.2f}"
        )
        # ── everything the ACCOUNT itself declares (2026-08-08) ────────────────────────────────
        # Added because two PU Prime demos of supposedly DIFFERENT tiers (Prime 700152904 and ECN
        # 700152905) came back byte-identical on the symbol specification — same `XAUUSD.p`, same
        # swap, same stops level — so nothing in this tool could tell them apart.
        #
        # ⚠ **The thing that actually separates those two tiers is COMMISSION, and commission is
        # not a symbol property.** MT5 publishes it nowhere on the spec; it lands on a filled deal
        # and only there. So treat this block as a search for a discriminator, NOT as one: if two
        # accounts match on every line here as well, the honest conclusion is that the terminal
        # cannot answer the question, and the answer is one 0.01-lot round turn on each and a read
        # of `mt5_ops.get_deal_breakdown()`.
        #
        # `leverage` and the two stop-out levels are the plausible tier-linked fields; `company`
        # and `margin_mode` are printed to catch an account that is quietly on a different entity.
        for name, val in (
            ("company", acct.company),
            ("leverage", f"1:{acct.leverage}"),
            ("margin_mode", acct.margin_mode),
            ("trade_mode", acct.trade_mode),
            ("margin_so_call", acct.margin_so_call),
            ("margin_so_so", acct.margin_so_so),
            ("limit_orders", acct.limit_orders),
            ("fifo_close", acct.fifo_close),
        ):
            print(f"  {name:<16} {val}")
        print()

        s = spec(mt5, symbol)
        print(f"SPECIFICATION - {s['symbol']}")
        for k in (
            "digits",
            "point",
            "contract_size",
            "tick_value",
            "tick_size",
            "volume_min",
            "volume_max",
            "volume_step",
            "stops_level_points",
            "freeze_level_points",
            "swap_long",
            "swap_short",
            "swap_mode",
            "swap_rollover_3days",
            "spread_now_points",
            "spread_float",
        ):
            print(f"  {k:<22} {s[k]}")

        pt = float(s["point"] or 0.01)
        print()
        print("READ THESE TWO CAREFULLY")
        print(
            f"  broker minimum stop  {s['stops_level_points']} points "
            f"= ${s['stops_level_points'] * pt:.2f} - enforced by the TERMINAL, independent of "
            f"exec_min_stop_mode"
        )
        print(
            f"  swap long / short    {s['swap_long']} / {s['swap_short']} - a POSITIVE value is "
            f"a credit paid TO you, and gold's short swap normally is one"
        )

        if args.symbols:
            sibs = sibling_symbols(mt5, symbol)
            print()
            print(f"SIBLING SYMBOLS - same market, quoted again on this terminal ({len(sibs)})")
            print(
                f"  {'symbol':<16} {'trade_mode':<11} {'swap_long':>10} {'swap_short':>11} "
                f"{'spread':>8}  path"
            )
            for r in sibs:
                sp = "-" if r["live_spread"] is None else f"{r['live_spread']:.3f}"
                print(
                    f"  {r['symbol']:<16} {r['trade_mode']:<11} {r['swap_long']:>10.2f} "
                    f"{r['swap_short']:>11.2f} {sp:>8}  {r['path']}"
                )
            pairs = {(r["swap_long"], r["swap_short"]) for r in sibs}
            if len(sibs) > 1 and len(pairs) > 1:
                print(
                    f"  -> {len(pairs)} DISTINCT swap pairs across {len(sibs)} quotes of one "
                    f"market. A cost is NOT safe to assume shared - measure the one you trade."
                )
            elif len(sibs) > 1:
                print(
                    "  -> every sibling carries the same swap on THIS account. That is a fact "
                    "about these symbols, and still says nothing about another ACCOUNT TIER."
                )
            else:
                print("  -> one quote only, so this terminal cannot speak for any other tier.")

        if args.sample > 0:
            print()
            print(f"SAMPLING the spread for {args.sample}s ...", flush=True)
            d = sample_spread(mt5, symbol, args.sample, pt)
            if not d.get("n"):
                print(f"  {d.get('note')}")
                print(
                    f"  ({d['stale_reads']} repeated ticks, {d.get('none_reads', 0)} no-answer "
                    f"reads, symbol_select -> {d.get('selected')})"
                )
            else:
                print(
                    f"  {d['n']} fresh reads ({d['stale_reads']} repeats, "
                    f"{d.get('none_reads', 0)} no-answer)"
                )
                print(
                    f"  min ${d['min']:.2f} | median ${d['median']:.2f} "
                    f"({d['median_points']:.0f} points) | p90 ${d['p90']:.2f} "
                    f"| p99 ${d['p99']:.2f} | max ${d['max']:.2f}"
                )
                print()
                print("  NOTE: a few minutes is a SNAPSHOT of one session, not the spread. Gold")
                print("  widens at the 17:00 NY rollover, around news and out of hours. Sample")
                print("  again in another session before quoting a median as the broker's cost.")

        if args.history_days > 0:
            print()
            print(f"STORED TICKS - last {args.history_days} day(s) ...", flush=True)
            h = history_spread(mt5, symbol, args.history_days, pt)
            if not h.get("n"):
                print(f"  {h.get('note')}")
            else:
                off = h["server_offset_h"]
                print(
                    f"  {h['n']:,} ticks over {h['days']} day(s); server clock measured at "
                    + (f"UTC{off:+d}" if off is not None else "UNKNOWN (no live tick)")
                )
                print(
                    f"  min ${h['min']:.2f} | median ${h['median']:.2f} "
                    f"({h['median_points']:.0f} points) | p90 ${h['p90']:.2f} "
                    f"| p99 ${h['p99']:.2f} | max ${h['max']:.2f}"
                )
                if not h["by_hour"]:
                    print(
                        "  by-hour breakdown SKIPPED - the server clock could not be measured, "
                        "and broker hours under a UTC heading is a wrong answer, not a partial one."
                    )
                else:
                    print("  by UTC hour (median / p99 / ticks):")
                for hr, v in h["by_hour"].items():
                    print(f"    {hr:02d}:00  ${v['median']:.2f}  ${v['p99']:.2f}  {v['n']:>8,}")
                print()
                print("  The 21:00-22:00 UTC band is the 17:00 NY rollover, where gold's spread")
                print("  widens and the swap is charged. A cost model that quotes only the")
                print("  overall median is understating what a trade held overnight pays.")
    finally:
        mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
