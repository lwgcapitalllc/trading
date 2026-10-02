"""Book a trade the bot never closed itself — off the broker's own deals — and say why.

Built 2026-10-02. The live SOS Fade bot halted while holding T369292543, a re-entry that only
existed because of a restart bug, and Aaron closed it by hand. A halted bot books nothing, and a
restart only books a close it can match against its own warm-up replay — so that trade's money
would have left the bot's record with nobody writing down what it made. Aaron: *"we need to
record that trade as well even though it was entered by a bug and managed by me."*

WHAT IT WRITES, into the bot's own decision ledger:
  * a `closed` row in the shape `algos/live/ledger.py` writes, so every reader that totals the
    bot's trades finds it — the money is the broker's (every deal of the position, costs apart),
    the risk is the one the bot recorded when it OPENED the trade;
  * with `--not-strategy`, the same `trade_not_strategy_performance` mark `mark_trade.py` writes,
    so the trade counts toward the account and never toward the strategy's edge.

WHAT IT REFUSES, rather than guessing (rule 1):
  * a ticket the bot has no `opened` row for — the R would have no risk under it;
  * a ticket that already has a `closed` row — it is never booked twice;
  * a position still open at the broker, or one whose deals cannot be read.

Read-only unless `--write` is given. Run ON THE BOX — the ledger and the terminal are there:
    python algos/tools/book_trade.py --bot sos_fade_demo --ticket 369292543 \\
        --why "..." --not-strategy
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import close_orphans as co  # noqa: E402  (one INSTANCES, one attach, one ledger writer)

try:  # the VPS console is cp1252
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

#: How the live bridge names a close a person made — `algos/live/bridge.py` MANUAL_CLOSE_REASON.
CLOSED_BY_YOU = "closed_by_you"


def ledger_rows(bot: str) -> list:
    """Every decision row the bot has written, oldest first. Torn lines are skipped."""
    out = []
    for path in sorted((co.INSTANCES / bot / "ledger").glob("decisions-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def find_open_and_close(rows: list, ticket: int):
    """(the `opened` row, the `closed` row or None) for this ticket."""
    opened = closed = None
    for r in rows:
        if r.get("ticket") != ticket:
            continue
        if r.get("event") == "opened":
            opened = r
        elif r.get("event") == "closed":
            closed = r
    return opened, closed


def closed_row(opened: dict, money: dict, close_price: float, reason: str) -> dict:
    """The `closed` row `Ledger.trade_closed` writes, built from the open row and the deals."""
    risk = opened.get("risk_usd")
    net = money["net_usd"]
    entry, intended = opened.get("price"), opened.get("intended_price")
    return {
        "kind": "trade",
        "event": "closed",
        "ticket": opened["ticket"],
        "dir": opened.get("dir"),
        "symbol": opened.get("symbol"),
        "intent": opened.get("intent") or "primary",
        "lots": opened.get("lots"),
        "price": close_price,
        "pnl_usd": net,
        "gross_usd": money["gross_usd"],
        "swap_usd": money["swap_usd"],
        "commission_usd": money["commission_usd"],
        "entry_price": entry,
        "intended_price": intended,
        "entry_slippage": (entry - intended) if entry and intended else None,
        # None, never 0, when the open row carried no risk: an R with nothing under it is an
        # unanswered question, not a scratch.
        "r": (net / float(risk)) if isinstance(risk, (int, float)) and risk else None,
        "reason": reason,
        "booked_by": "algos/tools/book_trade.py",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bot", required=True)
    ap.add_argument("--ticket", type=int, required=True)
    ap.add_argument("--why", required=True, help="one sentence: why the bot did not book it")
    ap.add_argument("--reason", default=CLOSED_BY_YOU, help="the close reason to record")
    ap.add_argument(
        "--not-strategy",
        action="store_true",
        help="also mark it as NOT the strategy's performance (counts toward the account only)",
    )
    ap.add_argument("--write", action="store_true", help="write; without it this only prints")
    a = ap.parse_args()

    opened, closed = find_open_and_close(ledger_rows(a.bot), a.ticket)
    if opened is None:
        raise SystemExit(f"REFUSING: {a.bot} has no 'opened' row for T{a.ticket}.")
    if closed is not None:
        raise SystemExit(f"REFUSING: T{a.ticket} is already booked ({closed.get('ts')}).")

    import MetaTrader5 as mt5

    cfg = co.load_cfg(a.bot)
    co.attach(mt5, cfg["mt5_path"], int(cfg["account"]))
    try:
        if mt5.positions_get(ticket=a.ticket):
            raise SystemExit(f"REFUSING: T{a.ticket} is still OPEN at the broker.")
        deals = mt5.history_deals_get(position=a.ticket) or ()
        money = co.realised(mt5, a.ticket)
    finally:
        mt5.shutdown()
    exits = [d for d in deals if d.entry == 1]  # DEAL_ENTRY_OUT
    if not exits or money["net_usd"] is None:
        raise SystemExit(f"REFUSING: the broker's deals for T{a.ticket} could not be read.")

    row = closed_row(opened, money, float(exits[-1].price), a.reason)
    print(json.dumps(row, indent=2, default=str))
    if not a.write:
        print("\ndry run - nothing written. Add --write to book it.")
        return
    path = co.ledger_write(a.bot, row)
    if a.not_strategy:
        co.ledger_write(
            a.bot,
            {
                "kind": "event",
                "event": "trade_not_strategy_performance",
                "counts_as_strategy_performance": False,
                "still_managed_by_the_bot": False,
                "ticket": a.ticket,
                "why": a.why,
                "marked_by": "algos/tools/book_trade.py",
            },
        )
    print(
        f"\nT{a.ticket} booked in {path.name}"
        + (" and marked not strategy." if a.not_strategy else ".")
    )


if __name__ == "__main__":
    main()
