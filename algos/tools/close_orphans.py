"""
Close positions a bot did NOT choose, and record them as mistakes rather than trades.

Built 2026-08-25 after the order-timeout incident: a broker request that TIMED OUT was read as
a request that FAILED, so the same limit was re-sent on five consecutive bars and five copies
of one order reached the broker. Four of the five positions were never a strategy decision.

WHAT THIS IS FOR, and what it deliberately is not:
  * It closes positions the bot is NOT managing, keeping the one it wrote down for itself.
  * It writes one record per closed ticket into the bot's own decision ledger, marked so that
    no later reader — human or tool — can count these as strategy performance. That marking is
    the POINT of the tool; closing is the easy half.
  * It is NOT a kill switch. `algos/tools/fleet_halt.py` is that. It never touches a position
    outside the bot's own magic, and it never closes the ticket you tell it to keep.

THE ONE RULE IT WAS BUILT AROUND, because it is the rule the incident broke:
  A broker call that times out has an UNKNOWN outcome, not a failed one. So this tool never
  decides anything from a return code. After every close it RE-READS the account and decides
  from what the broker actually holds. That is why it cannot repeat the fault it is cleaning up.

Read-only unless BOTH --close and the exact --confirm phrase are given.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:  # the VPS console is cp1252; degrading one character beats losing the report
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

REPO = Path(__file__).resolve().parents[2]
INSTANCES = REPO / "algos" / "markets" / "fx" / "instances"


# The phrase is not a password. It is a speed bump against a slip — the same reason the trading
# box's two write tools ask for one. It names the bot and the action so a command copied from
# somewhere else cannot run against the wrong instance.
def confirm_phrase(bot: str, n: int) -> str:
    return f"close {n} unmanaged positions on {bot}"


def load_cfg(bot: str) -> dict:
    p = INSTANCES / bot / "config.json"
    if not p.exists():
        raise SystemExit(f"no instance config at {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def attach(mt5, path: str, want_account: int):
    """Attach to an ALREADY-RUNNING terminal and refuse if it is not the right account.

    No login is attempted — the bot owns that. Lifted from broker_facts.py on purpose: the
    account assertion is the check that catches a terminal that switched logins under a running
    bot, which has happened here once already.
    """
    if not mt5.initialize(path=path):
        raise SystemExit(f"could not attach to {path}: {mt5.last_error()}")
    info = mt5.account_info()
    if info is None:
        mt5.shutdown()
        raise SystemExit("attached, but the terminal reports no account - is it logged in?")
    if int(info.login) != int(want_account):
        got, srv = info.login, info.server
        mt5.shutdown()
        raise SystemExit(
            f"WRONG TERMINAL: attached to account {got} on {srv}, expected {want_account}. "
            f"Refusing to close anything on an account this bot does not trade."
        )
    return info


def own_positions(mt5, symbol: str, magic: int) -> list:
    """This bot's open positions, newest ticket last. `None` from MT5 is an ERROR, not 'none
    open' — the two must never collapse, so an unreadable account raises instead of reading as
    a clean one."""
    pos = mt5.positions_get(symbol=symbol)
    if pos is None:
        raise SystemExit(f"positions_get returned None for {symbol}: {mt5.last_error()}")
    return sorted([p for p in pos if p.magic == magic], key=lambda p: p.ticket)


def describe(p) -> str:
    side = "LONG " if p.type == 0 else "SHORT"
    return (
        f"  T{p.ticket}  {side} {p.volume:>5}L  entry {p.price_open:>9.2f}  "
        f"stop {p.sl:>9.2f}  now {p.price_current:>9.2f}  "
        f"float {p.profit:>+9.2f}  swap {p.swap:>+7.2f}  opened {datetime.fromtimestamp(p.time, timezone.utc):%Y-%m-%d %H:%M}Z"
    )


def close_one(mt5, p) -> tuple:
    """Send one close. Returns (retcode, comment) and NOTHING is concluded from it — the caller
    re-reads the account. A timeout here means unknown, and unknown must never drive a retry."""
    bid, ask = mt5.symbol_info_tick(p.symbol).bid, mt5.symbol_info_tick(p.symbol).ask
    is_long = p.type == 0
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": p.symbol,
        "volume": p.volume,
        "type": mt5.ORDER_TYPE_SELL if is_long else mt5.ORDER_TYPE_BUY,
        "position": p.ticket,
        "price": bid if is_long else ask,
        "deviation": 20,
        "magic": p.magic,
        "comment": "ORPHAN-CLOSE",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    r = mt5.order_send(req)
    if r is not None and r.retcode == 10030:  # unsupported filling mode
        req["type_filling"] = mt5.ORDER_FILLING_FOK
        r = mt5.order_send(req)
    if r is None:
        return None, f"order_send returned None: {mt5.last_error()}"
    return r.retcode, getattr(r, "comment", "")


def realised(mt5, ticket: int) -> dict:
    """What the account actually booked for this position, in its parts. `None` anywhere means
    the broker could not be ASKED, never that the cost was zero."""
    deals = mt5.history_deals_get(position=ticket)
    if not deals:
        return {"gross_usd": None, "swap_usd": None, "commission_usd": None, "net_usd": None}
    gross = sum(d.profit for d in deals)
    swap = sum(d.swap for d in deals)
    comm = sum(d.commission for d in deals)
    return {
        "gross_usd": round(gross, 2),
        "swap_usd": round(swap, 2),
        "commission_usd": round(comm, 2),
        "net_usd": round(gross + swap + comm, 2),
    }


def ledger_write(bot: str, row: dict) -> Path:
    """Append one line to the bot's DECISION stream, in the shape `algos/live/ledger.py` writes.

    Written directly rather than by importing the live Ledger: this is a recovery tool run
    beside a bot that is up, and it has no business loading the live modules that bot is
    executing. The row shape is the contract, and it is one line long.
    """
    now = datetime.now(timezone.utc)
    d = INSTANCES / bot / "ledger"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"decisions-{now:%Y-%m-%d}.jsonl"
    full = {"ts": now.isoformat(timespec="seconds"), "bot": bot, **row}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(full, default=str) + "\n")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bot", required=True, help="instance key, e.g. sos_fade_demo")
    ap.add_argument(
        "--keep", type=int, help="the ONE ticket the bot is managing; it is never closed"
    )
    ap.add_argument(
        "--close", action="store_true", help="actually close; without it this only lists"
    )
    ap.add_argument("--confirm", default="", help="the exact phrase printed by a --close dry run")
    ap.add_argument(
        "--why",
        default="",
        help="one sentence recorded against every closed ticket saying what went wrong",
    )
    a = ap.parse_args()

    import MetaTrader5 as mt5

    cfg = load_cfg(a.bot)
    sym, magic = cfg["symbol"], int(cfg["magic"])
    acct = attach(mt5, cfg["mt5_path"], int(cfg["account"]))

    pos = own_positions(mt5, sym, magic)
    print(
        f"\naccount {acct.login} / {acct.server} / balance {acct.balance:,.2f} / equity {acct.equity:,.2f}"
    )
    print(f"{sym} under magic {magic}: {len(pos)} position(s)\n")
    for p in pos:
        mark = "  <- KEEP" if a.keep and p.ticket == a.keep else ""
        print(describe(p) + mark)

    if not pos:
        mt5.shutdown()
        return

    if a.keep is None:
        print("\nno --keep given, so nothing can be closed. Name the ticket the bot is managing.")
        mt5.shutdown()
        return

    if not any(p.ticket == a.keep for p in pos):
        mt5.shutdown()
        raise SystemExit(
            f"\nREFUSING: ticket {a.keep} is not open under this magic. The ticket to keep must be "
            f"one the broker actually holds. If it is gone, the bot's record is stale and that is "
            f"a different problem from this one."
        )

    doomed = [p for p in pos if p.ticket != a.keep]
    want = confirm_phrase(a.bot, len(doomed))
    if not a.close:
        print(f'\n{len(doomed)} would be closed. To do it:\n  --close --confirm "{want}"')
        mt5.shutdown()
        return
    if a.confirm.strip() != want:
        mt5.shutdown()
        raise SystemExit(f'\nREFUSING: --confirm must be exactly "{want}"')

    print(f"\nclosing {len(doomed)} unmanaged position(s)\n")
    closed, failed = [], []
    for p in doomed:
        snapshot = {
            "ticket": p.ticket,
            "dir": "bullish" if p.type == 0 else "bearish",
            "symbol": p.symbol,
            "lots": p.volume,
            "entry_price": p.price_open,
            "stop": p.sl,
            "opened_at": datetime.fromtimestamp(p.time, timezone.utc).isoformat(timespec="seconds"),
        }
        rc, comment = close_one(mt5, p)
        # ── the whole point: the ANSWER comes from the account, never from the return code ──
        time.sleep(0.5)
        still = {q.ticket for q in own_positions(mt5, sym, magic)}
        if p.ticket in still:
            failed.append((p.ticket, rc, comment))
            print(
                f"  T{p.ticket}  STILL OPEN - retcode={rc} '{comment}'. Not retried; re-run to try again."
            )
            continue
        money = realised(mt5, p.ticket)
        row = {
            "kind": "event",
            "event": "unmanaged_position_closed",
            # ⚠ THE FIELD THAT MATTERS. These tickets are in the broker's deal history and any
            # study built off the statement will find them. This says, next to the ticket, that
            # they were not the strategy's decision and must not be scored as its performance.
            "counts_as_strategy_performance": False,
            "closed_by": "algos/tools/close_orphans.py",
            "why": a.why or "not recorded",
            **snapshot,
            **money,
        }
        path = ledger_write(a.bot, row)
        closed.append((p.ticket, money["net_usd"]))
        print(f"  T{p.ticket}  closed, net {money['net_usd']}  -> recorded in {path.name}")

    if closed:
        ledger_write(
            a.bot,
            {
                "kind": "event",
                "event": "unmanaged_positions_incident",
                "counts_as_strategy_performance": False,
                "tickets": [t for t, _ in closed],
                "net_usd": round(sum(n for _, n in closed if n is not None), 2),
                "kept_ticket": a.keep,
                "why": a.why or "not recorded",
            },
        )

    left = own_positions(mt5, sym, magic)
    print(f"\n{len(left)} position(s) remain under magic {magic}:")
    for p in left:
        print(describe(p))
    if failed:
        print(
            f"\n{len(failed)} did NOT close. Nothing was retried - re-run and it will re-read the account first."
        )
    mt5.shutdown()


if __name__ == "__main__":
    main()
