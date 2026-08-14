#!/usr/bin/env python3
"""fleet_halt.py — pull, release or read the switch that stops every bot placing orders.

The switch itself is one file and the bots read it directly (`algos/shared/fleet_halt.py`), so this
tool is a convenience, not the mechanism. That is deliberate: **the switch has to be pullable
without this script**, because the day you need it is the day something is broken, and a Python
entry point that will not start is a switch that does not exist. Both of these do the same thing:

    python algos/tools/fleet_halt.py --on "spread blew out"
    ssh forexvps "echo spread blew out > C:\\trading\\algos\\FLEET_HALT"

⚠ **Pulling it does NOT close anything.** Open positions keep their broker-side stops and the bots
keep running, observing and writing their ledgers. It stops NEW orders. Flattening a book is a
trading decision and a safety device must not take one.

⚠ **Releasing it does NOT resume trading.** The halt latches inside each bot process, so clearing
the flag is only half the job — the bots have to be RESTARTED. `--off` says so every time rather
than leaving you to remember it, because "I turned it off and nothing traded" is the failure this
tool can actually prevent.

Usage:
    python algos/tools/fleet_halt.py --status
    python algos/tools/fleet_halt.py --on "why"
    python algos/tools/fleet_halt.py --off
"""

from __future__ import annotations

import argparse
import getpass
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "algos" / "shared") not in sys.path:
    sys.path.insert(0, str(_ROOT / "algos" / "shared"))

from fleet_halt import flag_path, read_fleet_halt  # noqa: E402


def _stamp(reason: str) -> str:
    """WHO, WHERE, WHEN and WHY, in that order, because the reader of this file is a person at
    3am who has just found the fleet stopped and does not yet know whether it was them."""
    who = f"{getpass.getuser()}@{socket.gethostname()}"
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    return f"{reason.strip()}\n(set by {who} at {when})\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--on",
        metavar="REASON",
        help="halt the fleet. The reason is written into the flag and reaches Telegram.",
    )
    g.add_argument(
        "--off",
        action="store_true",
        help="clear the flag. Does NOT resume trading — restart the bots.",
    )
    g.add_argument("--status", action="store_true", help="read the switch without changing it")
    args = ap.parse_args(argv)

    path = flag_path()

    if args.status:
        r = read_fleet_halt()
        print(f"flag: {path}")
        print(f"state: {r.kind.upper()}")
        if r.halted:
            print(f"reason: {r.reason}")
            if not r.readable:
                # The distinction the `readable` field exists for. A human seeing "HALTED" and a
                # reason they wrote is a different situation from a human seeing "HALTED" because
                # the box cannot read its own filesystem, and one of those needs a different fix.
                print(
                    "⚠ this is NOT a halt somebody requested — the switch could not be READ, "
                    "and every bot halts itself when that happens. Fix the filesystem."
                )
        return 0

    if args.on:
        # No refusal when it is already set, and no clever merge: re-pulling an already-pulled
        # switch with a fresher reason is a thing somebody will do under pressure, and it should
        # simply work.
        path.write_text(_stamp(args.on), encoding="utf-8")
        print(f"FLEET HALTED — wrote {path}")
        print("Running bots stop placing orders on their next poll (~10s).")
        print("Open positions keep their broker stops. Nothing is closed.")
        return 0

    # --off
    try:
        path.unlink()
        print(f"cleared {path}")
    except FileNotFoundError:
        print(f"nothing to clear — {path} is not there")
    except OSError as e:
        # Loud and non-zero: a flag that will not delete means the fleet stays halted, and the
        # one thing that must not happen is this printing something reassuring.
        print(f"COULD NOT CLEAR {path}: {e}", file=sys.stderr)
        print("The fleet stays halted until this file is gone.", file=sys.stderr)
        return 1
    print(
        "⚠ This does NOT resume trading. The halt latches inside each bot process — "
        "restart the bots (schtasks /run /tn SYS_STARTUP)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
