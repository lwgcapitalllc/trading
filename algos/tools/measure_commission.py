"""measure_commission.py — read a symbol's COMMISSION by trading it, on a demo account only.

    python algos/tools/measure_commission.py --path C:\\MT5_Demo\\terminal64.exe \\
        --account 700152905 --symbol GBPJPY.p

**Why this has to place a trade at all.** Commission is the one broker cost MT5 does not put on
a symbol specification — it lands on a filled DEAL. `broker_facts.py` reads everything that can
be read without trading; this reads the one thing that cannot. `backtest/fills.py` said outright
that commission was the cost nobody here had measured, and the only instrument that can settle
it is a filled deal.

⚠ **It opens ONE minimum-size position and closes it immediately.** That is the entire trade.
It sets no stop and no target because it holds the position for under a second and a stop would
add a rejection path to a tool whose only job is to read a number.

⚠ **DEMO ONLY, and the check is NOT `trade_mode`.** PU Prime's demo account 700152905 reports
`account_info().trade_mode == 0`, which is MT5's code for a REAL account — the flag that looks
like the obvious guard is wrong on the very account this tool was written for. So the refusals
are the ones that cannot lie: the caller must NAME the account it expects, the login must match
it, and the server name must end in `-Demo`. All three, or it refuses. That is this repo's
no-vs-cannot-ask rule applied to a guard: a check whose healthy answer and whose dangerous
answer look identical is not a check.

⚠ **It is a DIAGNOSTIC and must never grow into a bot.** It deliberately does not go through
`BotMT5.place_order`: that seam needs an instance config, a magic number and a strategy, and a
one-shot measurement has none of them. The trade-off is that the volume and account guards below
are this file's own. If this file ever needs a stop, a target or a second position, it has become
something else and belongs behind the bot seam instead.
"""

from __future__ import annotations

import argparse
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

MAX_LOTS = 0.02  # a hard ceiling independent of what the broker's minimum turns out to be


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Measure a symbol's commission. Demo accounts only.")
    ap.add_argument("--path", required=True, help="terminal64.exe of a running, logged-in terminal")
    ap.add_argument(
        "--account", type=int, required=True, help="the account you EXPECT; refuses on mismatch"
    )
    ap.add_argument("--symbol", required=True)
    args = ap.parse_args(argv)

    import MetaTrader5 as mt5

    if not mt5.initialize(path=args.path):
        raise SystemExit(f"could not attach to {args.path}: {mt5.last_error()}")

    info = mt5.account_info()
    if info is None:
        mt5.shutdown()
        raise SystemExit("attached, but the terminal reports no account - is it logged in?")
    if int(info.login) != int(args.account):
        got, srv = info.login, info.server
        mt5.shutdown()
        raise SystemExit(f"WRONG TERMINAL: attached to {got} on {srv}, expected {args.account}.")
    if not str(info.server).endswith("-Demo"):
        srv = info.server
        mt5.shutdown()
        raise SystemExit(
            f"REFUSING: server {srv!r} is not a demo server. This tool places a real order and "
            f"will only do it on an account whose server name ends in '-Demo'."
        )

    print(f"account {info.login} / {info.server} / balance {info.balance:,.2f}")

    if not mt5.symbol_select(args.symbol, True):
        mt5.shutdown()
        raise SystemExit(f"could not select {args.symbol} into Market Watch")

    si = mt5.symbol_info(args.symbol)
    if si is None:
        mt5.shutdown()
        raise SystemExit(f"no symbol info for {args.symbol}")

    lots = float(si.volume_min)
    if lots > MAX_LOTS:
        mt5.shutdown()
        raise SystemExit(f"REFUSING: broker minimum {lots} exceeds this tool's ceiling {MAX_LOTS}.")

    open_now = mt5.positions_get(symbol=args.symbol) or []
    if open_now:
        mt5.shutdown()
        raise SystemExit(
            f"REFUSING: {len(open_now)} position(s) already open on {args.symbol}. This tool "
            f"closes what it opens by matching the symbol, so it will not run beside another."
        )

    tick = mt5.symbol_info_tick(args.symbol)
    if tick is None:
        mt5.shutdown()
        raise SystemExit(f"no tick for {args.symbol} - market shut, or symbol not streaming")

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": args.symbol,
        "volume": lots,
        "type": mt5.ORDER_TYPE_BUY,
        "price": tick.ask,
        "deviation": 50,
        "comment": "commission probe",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    print(f"OPENING {lots} {args.symbol} at {tick.ask} ...")
    res = mt5.order_send(req)
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        mt5.shutdown()
        raise SystemExit(
            f"open REJECTED: {res.retcode if res else 'no result'} {res.comment if res else mt5.last_error()}"
        )
    ticket = res.order
    print(f"  filled at {res.price}, deal order {ticket}")

    time.sleep(1.0)
    pos = mt5.positions_get(symbol=args.symbol) or []
    if not pos:
        mt5.shutdown()
        raise SystemExit("opened but no position found to close - CHECK THE TERMINAL BY HAND.")

    p = pos[0]
    tick = mt5.symbol_info_tick(args.symbol)
    close = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": args.symbol,
        "volume": p.volume,
        "type": mt5.ORDER_TYPE_SELL,
        "position": p.ticket,
        "price": tick.bid,
        "deviation": 50,
        "comment": "commission probe close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    print(f"CLOSING position {p.ticket} at {tick.bid} ...")
    res2 = mt5.order_send(close)
    if res2 is None or res2.retcode != mt5.TRADE_RETCODE_DONE:
        mt5.shutdown()
        raise SystemExit(
            f"CLOSE REJECTED: {res2.retcode if res2 else 'no result'}. A POSITION IS OPEN ON "
            f"{args.symbol} - CLOSE IT BY HAND NOW."
        )
    print(f"  closed at {res2.price}")

    # Read what the round trip actually cost, by deal, so commission is separated from the
    # price move and from swap rather than netted into one number that cannot be decomposed.
    time.sleep(1.5)
    deals = mt5.history_deals_get(position=p.ticket) or []
    comm = sum(float(d.commission) for d in deals)
    swap = sum(float(d.swap) for d in deals)
    gross = sum(float(d.profit) for d in deals)
    vol = sum(float(d.volume) for d in deals if d.volume)
    print()
    print(f"DEALS ON POSITION {p.ticket}: {len(deals)}")
    for d in deals:
        print(
            f"  {d.ticket} vol {d.volume} commission {d.commission} swap {d.swap} profit {d.profit}"
        )
    print()
    print(f"  commission total  {comm:.4f} over {vol:.2f} lots across {len(deals)} deal(s)")
    if vol:
        print(f"  COMMISSION PER LOT PER SIDE  {comm / vol:.4f}")
        print("  (sign is MT5's own: a negative number is a charge)")
    print(f"  swap {swap:.4f} | gross price move {gross:.4f}")
    print()
    print("Paste the per-lot-per-side figure into backtest/fills.py as a MEASURED profile.")
    mt5.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
