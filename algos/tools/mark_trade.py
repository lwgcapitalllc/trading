"""Record that a trade must NOT be counted as the strategy's performance.

Some trades reach the book without the strategy choosing them: duplicate orders from a broker
timeout, a re-entry a guard should have blocked, a hand trade under the bot's magic. They live in
the broker's deal history for good, so **anything totalling the account will find them and score
them** — and a windfall nobody labelled becomes evidence for the strategy the next time somebody
adds the numbers up.

⚠ **This changes NOTHING about how the bot treats the trade.** The bot goes on managing it
normally — stop, targets, time exit — which is usually what you want: a trade that should not
exist should still be exited properly. This is a note for whoever reads the record later, and
that is deliberately all it is.

⚠ **It marks by TICKET**, because the ticket is the one thing the ledger and the broker statement
share. Whoever joins the two later can find it.

Companion to `close_orphans.py`, which closes AND marks. Use this one when the trade is staying.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:  # the VPS console is cp1252
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

INSTANCES = Path(__file__).resolve().parents[2] / "algos" / "markets" / "fx" / "instances"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bot", required=True)
    ap.add_argument("--ticket", type=int, required=True)
    ap.add_argument("--why", required=True, help="one sentence: what put this trade on the book")
    a = ap.parse_args()

    d = INSTANCES / a.bot / "ledger"
    if not d.is_dir():
        raise SystemExit(f"no ledger at {d}")
    now = datetime.now(timezone.utc)
    row = {
        "ts": now.isoformat(timespec="seconds"),
        "bot": a.bot,
        "kind": "event",
        "event": "trade_not_strategy_performance",
        "counts_as_strategy_performance": False,
        "still_managed_by_the_bot": True,
        "ticket": a.ticket,
        "why": a.why,
        "marked_by": "algos/tools/mark_trade.py",
    }
    path = d / f"decisions-{now:%Y-%m-%d}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    print(f"T{a.ticket} marked in {path.name}: not strategy performance, still managed.")


if __name__ == "__main__":
    main()
