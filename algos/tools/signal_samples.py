"""Send one example of EVERY alert thread shape — setups to the signals chat, trades to the
trades chat (`--trades`).

⚠ Nothing here writes a message. Every string comes out of the real `alerts.format_*` functions
driven by real `SetupSnapshot` objects, so what lands in Telegram is byte-identical to what the
live bot would send for the same setup. Hand-typing the samples would show wording that does not
exist, which is the whole thing this is meant to check.

🔴 **The TRADES mode exists so the thread can be READ before it ships (2026-09-22).** A live bot
runs a frozen `deployed/` snapshot, so new wording does not reach a phone until a promote — and
promoting two live bots to look at a message is the wrong order to do things in. `--dry-run
--trades` prints the whole story to a terminal; `--trades` puts it in the trades room, threaded, so
what is approved is what will actually arrive.

⚠ **`--trades` posts into the room that carries real fills.** The header says so and the footer
closes it, exactly as the signals samples do, and both are meant to be deleted afterwards.

Run on the VPS (it has credentials.json):
    python C:\\trading\\algos\\tools\\signal_samples.py --dry-run
    python C:\\trading\\algos\\tools\\signal_samples.py
    python C:\\trading\\algos\\tools\\signal_samples.py --trades --dry-run
    python C:\\trading\\algos\\tools\\signal_samples.py --trades
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "algos" / "live", ROOT / "algos" / "shared"):
    sys.path.insert(0, str(p))

import alerts  # noqa: E402
from notify import SIGNAL, TRADE, send_telegram_id  # noqa: E402

from backtest.setups import (
    DEAD,
    FILLED,
    RESTING,  # noqa: E402
    WATCHING,
    Confluence,
    SetupSnapshot,
)

STRAT, SYM = "SosFadeStrategy", "XAUUSD.p"
DISPLAY = "SOS Fade"


def snap(**kw) -> SetupSnapshot:
    base = dict(key="sample", strategy=STRAT, symbol=SYM, side=1, state=WATCHING)
    base.update(kw)
    return SetupSnapshot(**base)


def conf(arm: str, sos: bool, zone: str, zone_met: bool):
    return (
        Confluence("Arm", True, arm),
        Confluence("Shift of structure", sos, "confirmed"),
        Confluence("Retrace zone", zone_met, zone),
    )


NOT_YET = "not tagged yet"
FVG_LIVE = "0.5-0.886 tagged, FVG live"
NO_FVG = "0.5-0.886 tagged, but no FVG in it"

# Each thread is (title, root_snapshot, [reply snapshots in order]).
# Between them these cover: both directions, all three zone wordings, 2-of-3 and 3-of-3, an order
# resting at 2 of 3, one blocking rule and three, a block that LIFTS, and all six ways a setup
# dies that the strategy has a sentence for.
THREADS = [
    (
        "1. The ordinary death — price never came back",
        snap(
            side=1,
            confluences=conf("swept Day Low", True, NOT_YET, False),
            zone=(3312.40, 3298.15),
            stop=3297.65,
        ),
        [
            snap(
                side=1,
                state=DEAD,
                confluences=conf("swept Day Low", True, NOT_YET, False),
                reason="No retrace — Price never retraced into the 0.5-0.886 band, so the entry zone was never "
                "reached. This is the ordinary way a setup dies.",
            )
        ],
    ),
    (
        "2. Reached the zone, nothing to rest a limit on",
        snap(
            side=-1,
            confluences=conf("swept Week High", True, NOT_YET, False),
            zone=(3401.80, 3417.25),
            stop=3417.75,
        ),
        [
            snap(
                side=-1,
                state=DEAD,
                confluences=conf("swept Week High", True, NO_FVG, False),
                reason="No FVG in zone — Price DID reach the 0.5-0.886 band, but no fair-value gap overlapped it while "
                "price was there — there was nothing to rest a limit on.",
            )
        ],
    ),
    (
        "3. The one you want — forming, resting, filled",
        snap(
            side=1,
            confluences=conf("swept Prev Day Low", True, NOT_YET, False),
            zone=(3288.90, 3271.40),
            stop=3270.90,
        ),
        [
            snap(
                side=1,
                state=RESTING,
                confluences=conf("swept Prev Day Low", True, FVG_LIVE, True),
                zone=(3288.90, 3271.40),
                entry=3279.60,
                stop=3270.90,
                targets=(3296.10, 3311.75, 3334.20),
            ),
            snap(
                side=1, state=FILLED, confluences=conf("swept Prev Day Low", True, FVG_LIVE, True)
            ),
        ],
    ),
    (
        "4. An order RESTING at 2 of 3 — the limit is real, price has not come to it",
        snap(
            side=-1,
            confluences=conf("swept Asia High", True, NOT_YET, False),
            zone=(3358.20, 3372.90),
            stop=3373.40,
        ),
        [
            snap(
                side=-1,
                state=RESTING,
                confluences=conf("swept Asia High", True, NOT_YET, False),
                zone=(3358.20, 3372.90),
                entry=3366.05,
                stop=3373.40,
                targets=(3351.30, 3338.60, 3320.15),
            ),
            snap(
                side=-1,
                state=DEAD,
                confluences=conf("swept Asia High", True, NOT_YET, False),
                reason="Never filled — All three confluences met and the limit rested — price never came back to "
                "touch it.",
            ),
        ],
    ),
    (
        "5. Blocked by ONE of your rules, then died",
        snap(
            side=1,
            confluences=conf("RSI divergence", True, NOT_YET, False),
            zone=(3305.60, 3290.10),
            stop=3289.60,
        ),
        [
            snap(
                side=1,
                confluences=conf("RSI divergence", True, FVG_LIVE, True),
                blocked_by=("Divergence / extreme-RSI veto",),
            ),
            snap(
                side=1,
                state=DEAD,
                confluences=conf("RSI divergence", True, FVG_LIVE, True),
                reason="Divergence / RSI veto — All three confluences met. The divergence / extreme-RSI veto refused the "
                "entry.",
            ),
        ],
    ),
    (
        "6. Blocked by THREE rules at once",
        snap(
            side=-1,
            confluences=conf("swept Day High", True, NOT_YET, False),
            zone=(3390.15, 3404.80),
            stop=3405.30,
        ),
        [
            snap(
                side=-1,
                confluences=conf("swept Day High", True, FVG_LIVE, True),
                blocked_by=(
                    "Divergence / extreme-RSI veto",
                    "Final hour (16:00-18:00 New York)",
                    "HTF breakout / bias filter",
                ),
            ),
            snap(
                side=-1,
                state=DEAD,
                confluences=conf("swept Day High", True, FVG_LIVE, True),
                reason="Final hour — All three confluences met. The final-hour rule (16:00-18:00 New York) refused "
                "the entry.",
            ),
        ],
    ),
    (
        "7. Blocked, the rule LIFTED, and it traded anyway",
        snap(
            side=1,
            confluences=conf("swept Prev Week Low", True, NOT_YET, False),
            zone=(3264.70, 3248.35),
            stop=3247.85,
        ),
        [
            snap(
                side=1,
                confluences=conf("swept Prev Week Low", True, FVG_LIVE, True),
                blocked_by=("HTF breakout / bias filter",),
            ),
            snap(
                side=1,
                state=RESTING,
                confluences=conf("swept Prev Week Low", True, FVG_LIVE, True),
                zone=(3264.70, 3248.35),
                entry=3256.10,
                stop=3247.85,
                targets=(3273.40, 3287.90, 3309.55),
            ),
            snap(
                side=1, state=FILLED, confluences=conf("swept Prev Week Low", True, FVG_LIVE, True)
            ),
        ],
    ),
    (
        "8. Refused by the higher-timeframe filter",
        snap(
            side=-1,
            confluences=conf("swept Session High", True, NOT_YET, False),
            zone=(3345.05, 3359.60),
            stop=3360.10,
        ),
        [
            snap(
                side=-1,
                state=DEAD,
                confluences=conf("swept Session High", True, FVG_LIVE, True),
                reason="HTF filter — All three confluences met. The HTF breakout / bias filter refused the "
                "entry.",
            )
        ],
    ),
]


def render(s: SetupSnapshot, is_root: bool) -> str:
    """Exactly the routing `SetupAlerts._handle` uses, so the sample cannot drift from the bot."""
    if is_root:
        return alerts.format_watching(s, 2, DISPLAY)
    if s.blocked_by:
        return alerts.format_blocked(s)
    if s.state == RESTING:
        return alerts.format_entry_zone(s)
    return alerts.format_resolved(s)


# ── the TRADES room — one trade's whole life, as the thread will read it ─────────────────────
#
# 🔴 **Every string below comes out of the real `alerts.format_*` functions**, exactly as the
# setup samples do, so what lands here is byte-identical to what the bridge sends for the same
# trade. Hand-typing them would show wording that does not exist, which is what this tool is for.
#
# Between them these cover: a winner managed the whole way (breakeven, an add, a trail, a rung
# banked), a loser that only ever had its stop tightened, and the scratch — a stop moved to entry
# and then hit, which the verdict calls BREAKEVEN rather than filing beside the real losers.

_ENTRY = dict(strategy=DISPLAY, symbol=SYM, digits=2)


def _trade_threads():
    """(title, root, [replies]) for each trade shape. A function, not a constant, so the module
    still imports on a box whose `alerts` predates these formatters — the signals mode is the one
    that runs unattended and must not be taken down by the samples beside it."""
    return [
        (
            "1. The one you want — managed the whole way",
            alerts.format_entry(
                **_ENTRY,
                direction="LONG",
                entry=3290.00,
                stop=3280.00,
                lots=0.25,
                risk_usd=250.00,
                risk_pct=5.0,
            ),
            [
                alerts.format_stop_moved(
                    direction=1, entry=3290.00, was=3280.00, now=3290.00, opening_stop=3280.00
                ),
                alerts.format_scaled_in(
                    lots_added=0.12, lots_now=0.37, price=3305.00, stop=3296.00
                ),
                alerts.format_stop_moved(
                    direction=1, entry=3290.00, was=3290.00, now=3301.50, opening_stop=3280.00
                ),
                alerts.format_partial_banked(lots_banked=0.12, lots_before=0.37, lots_after=0.25),
                alerts.format_exit(
                    strategy=DISPLAY,
                    symbol=SYM,
                    exit_price=3320.00,
                    pnl_usd=712.50,
                    r_multiple=2.85,
                    exit_reason="target",
                ),
            ],
        ),
        (
            "2. The loser — the stop only ever came closer",
            alerts.format_entry(
                **_ENTRY,
                direction="SHORT",
                entry=3290.00,
                stop=3302.00,
                lots=0.20,
                risk_usd=240.00,
                risk_pct=5.0,
            ),
            [
                alerts.format_stop_moved(
                    direction=-1, entry=3290.00, was=3302.00, now=3296.00, opening_stop=3302.00
                ),
                alerts.format_exit(
                    strategy=DISPLAY,
                    symbol=SYM,
                    exit_price=3296.00,
                    pnl_usd=-126.40,
                    r_multiple=-0.53,
                    exit_reason="stop",
                ),
            ],
        ),
        (
            "3. The scratch — out of risk, then stopped at entry",
            alerts.format_entry(
                **_ENTRY,
                direction="LONG",
                entry=3290.00,
                stop=3280.00,
                lots=0.25,
                risk_usd=250.00,
                risk_pct=5.0,
            ),
            [
                alerts.format_stop_moved(
                    direction=1, entry=3290.00, was=3280.00, now=3290.00, opening_stop=3280.00
                ),
                alerts.format_exit(
                    strategy=DISPLAY,
                    symbol=SYM,
                    exit_price=3289.85,
                    pnl_usd=-12.50,
                    r_multiple=-0.02,
                    exit_reason="stop moved to entry",
                ),
            ],
        ),
    ]


TRADE_HEADER = (
    "🧪 EXAMPLES — none of these are live trades, and no order exists.\n"
    "Three sample threads follow: a winner managed the whole way, a loser, and a scratch. Every "
    "message is rendered by the same code the bot sends with. Delete this block when you are done."
)
TRADE_FOOTER = "🧪 End of examples. Everything after this line is real."


HEADER = (
    "🧪 EXAMPLES — none of these are live setups.\n"
    "Eight sample threads follow, one per shape a real setup can take. Every message is "
    "rendered by the same code the bot sends with. Delete this block when you are done.\n"
    "Anything above this line was an incomplete earlier run — delete that too."
)
FOOTER = "🧪 End of examples. Everything after this line is real."


#: 🔴 MEASURED, not guessed: at 1.2s this ran into `429 Too Many Requests, retry after 26` and
#: FOUR of twenty-four messages never landed — leaving replies whose root was missing, which is
#: the one outcome that makes the samples unreadable. Telegram's group ceiling is ~20 messages a
#: minute, so 3.5s (≈17/min) sits under it with room. The live bot cannot hit this — it sends at
#: most a handful an hour — so the limit belongs to this tool, not to `notify.py`.
_GAP_SECONDS = 3.5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print, send nothing")
    ap.add_argument(
        "--trades",
        action="store_true",
        help="one example of every TRADE thread shape, into the trades room, instead of the setups",
    )
    args = ap.parse_args()
    tally = {"ok": 0, "failed": 0}

    def send(text, reply_to):
        """One send, with its room named LITERALLY on each branch.

        🔴 **A `room` variable would route correctly and be invisible to
        `test_notification_routing`**, whose whole job is to grep every send in this repo for a
        stated kind — so the guard would go on passing over a call site that had stopped naming
        one. Routing quietly is the failure the kinds exist to end, and a guard that cannot see a
        call site is the same failure wearing a green tick.
        """
        if args.trades:
            return send_telegram_id(text, TRADE, reply_to=reply_to)
        return send_telegram_id(text, SIGNAL, reply_to=reply_to)

    def post(text, reply_to=None):
        if args.dry_run:
            print(("  └ " if reply_to else "") + text.replace("\n", "\n     ") + "\n")
            tally["ok"] += 1
            return 1
        mid = send(text, reply_to)
        if mid is None:
            # One retry, after long enough for any rate-limit window to clear. A root that fails
            # orphans every reply under it, so this is worth the wait.
            time.sleep(30)
            mid = send(text, reply_to)
        tally["ok" if mid is not None else "failed"] += 1
        time.sleep(_GAP_SECONDS)
        return mid

    threads = _trade_threads() if args.trades else THREADS
    post(TRADE_HEADER if args.trades else HEADER)
    for title, root, replies in threads:
        if args.dry_run:
            print(f"\n=== {title} ===")
        # A trade sample is already a rendered string; a setup sample is a snapshot the bot's own
        # routing turns into one. Both go through the same posting path below, so the rate limit,
        # the retry and the honest tally are stated once.
        rid = post(root if args.trades else render(root, True))
        for r in replies:
            post(r if args.trades else render(r, False), reply_to=rid)
    post(TRADE_FOOTER if args.trades else FOOTER)

    # ⚠ Reports what LANDED, never what was attempted. The first run of this printed
    # "sent: 24 messages" while four had been refused — the repo's own rule about never recording
    # a request as a receipt, in the tool written to check the messages.
    total = sum(1 + len(r) for _, _, r in threads) + 2
    verb = "would send" if args.dry_run else "sent"
    print(
        f"{verb}: {tally['ok']} of {total} messages"
        + (f" — {tally['failed']} FAILED" if tally["failed"] else "")
    )
    return 1 if tally["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
