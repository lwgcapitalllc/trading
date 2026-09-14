"""
verify_channel.py — post a test message to a Telegram channel, from the box.

An account's trade and signal channels are typed in by a person, and a chat id that is one digit
wrong, or one the bot has not been added to, fails in exactly the way this whole design exists to
prevent: **silently, at the moment a real fill arrives.** Telegram answers a bad id with a 400 that
reaches a log nobody opens, so the only honest way to know a channel works is to post to it.

🔴 **IT RUNS ON THE BOX, and that is the point rather than a convenience.** The Telegram token
lives in the box's git-ignored `algos/credentials.json` and nowhere else, so a test posted from a
laptop would be testing a different sender from the one that will carry the fills — a bot can only
post to a chat it belongs to, so "it worked from my machine" says nothing about the bot that
matters. The Command Center drives this over SSH for that reason.

⚠ **It sends and reports; it writes NOTHING.** Saving the channel is the Command Center's job, and
a tool that both tested and saved would make a failed test look like a saved one.

Usage, from `C:\\trading`:

    python algos/tools/verify_channel.py --chat-id -1004410831757 --kind trade
    python algos/tools/verify_channel.py --account 34957946 --kind signal

`--chat-id` tests an id a person has just typed, BEFORE it is saved anywhere. `--account` tests
what that account's registry row already names, which is what proves a live bot can report.

Exit 0 = the message landed. Anything else = it did not, and the reason is on stdout.
"""

import argparse
import sys
from pathlib import Path

_ALGOS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ALGOS / "shared"))

# Everything this prints is ASCII. The box's console is cp1252 and one unencodable character
# raises mid-print, so a successful test would read as a crash — the trap `broker_facts.py`
# already records. `errors="replace"` is the belt; ASCII text is the braces.
try:  # pragma: no cover - depends on the stream, not on the logic
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:  # noqa: BLE001
    pass


def message(kind: str, account, chat_id: str) -> str:
    """What gets posted. Plain text, no Markdown — see `notify.send_telegram_id`.

    ⚠ It says WHICH channel it is and WHY it arrived, because the person reading it is often not
    the person who pressed the button: an unexplained message in a channel somebody has just been
    given reads as a bot misbehaving.
    """
    where = f"account {account}" if account is not None else "a channel being set up"
    return (
        f"TEST MESSAGE - {kind} channel\n"
        f"This channel has been entered as the {kind} channel for {where}.\n"
        f"Chat {chat_id}.\n"
        f"Nothing is trading because of this message. If you did not expect it, "
        f"tell whoever set the account up."
    )


def run(kind: str, account=None, chat_id: str = "") -> int:
    from notify import ACCOUNT_ROOM_KEYS, account_rooms, send_telegram_id

    if kind not in ACCOUNT_ROOM_KEYS:
        print(f"FAIL: unknown channel kind {kind!r} - expected one of {sorted(ACCOUNT_ROOM_KEYS)}")
        return 2
    dest = str(chat_id or "").strip()
    if not dest:
        # 🔴 THREE ANSWERS, never two. An account that names no channel of this kind and an account
        # registry that could not be read call for different work — enter the channel, or fix the
        # file — and reporting both as "not set" sends somebody to do the wrong one.
        rooms = account_rooms(account)
        if rooms is None:
            print(
                "FAIL: the account registry could not be read, so there is nothing to test. "
                "Check algos/markets/fx/accounts.json on the box."
            )
            return 3
        dest = rooms.get(kind, "")
        if not dest:
            print(f"FAIL: account {account} names no {kind} channel, so there is nothing to test.")
            return 4

    # 🔴 Straight through `send_telegram_id` with the id as an OVERRIDE, so this tests the exact
    # sender a bot uses — same token, same transport, same plain-text mode. A tool that built its
    # own request would be a second implementation, and it would pass on the day the real one is
    # broken. The override also means the routing rules are deliberately NOT consulted: the
    # question here is "can the bot post to this id", not "where would a message go".
    #
    # ⚠ The kind is passed as TRADE/SIGNAL/HEALTH anyway so a missing override could never fall
    # through to a real room silently — `dest` is non-empty by the time we get here.
    msg_id = send_telegram_id(
        message(kind, account, dest),
        kind,
        chat_id=dest,
        markdown=False,
    )
    if msg_id is None:
        # The reason is already on stdout: `notify` prints whatever Telegram said. It is the
        # product of this tool, so it must not be swallowed and re-worded here.
        print(f"FAIL: could not post to {dest}. See the line above for what Telegram said.")
        return 1
    print(f"OK: posted to {dest} as message {msg_id}.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Post a test message to a Telegram channel.")
    ap.add_argument("--kind", required=True, help="trade, signal or health")
    ap.add_argument("--account", type=int, default=None, help="the broker login being set up")
    ap.add_argument("--chat-id", default="", help="test this id instead of the saved one")
    args = ap.parse_args(argv)
    if args.account is None and not args.chat_id:
        print("FAIL: pass --chat-id, --account, or both.")
        return 2
    try:
        return run(args.kind, args.account, args.chat_id)
    except Exception as exc:  # noqa: BLE001
        # Broad on purpose: this tool's whole output is a verdict, and an unhandled traceback over
        # SSH reads to the Command Center as "no answer" rather than as a failure.
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
