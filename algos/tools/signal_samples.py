"""Send one example of EVERY setup-alert thread shape to the signals chat.

⚠ Nothing here writes a message. Every string comes out of the real `alerts.format_*` functions
driven by real `SetupSnapshot` objects, so what lands in Telegram is byte-identical to what the
live bot would send for the same setup. Hand-typing the samples would show wording that does not
exist, which is the whole thing this is meant to check.

Run on the VPS (it has credentials.json):
    python C:\\trading\\algos\\tools\\signal_samples.py --dry-run
    python C:\\trading\\algos\\tools\\signal_samples.py
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "algos" / "live", ROOT / "algos" / "shared"):
    sys.path.insert(0, str(p))

import alerts                                                          # noqa: E402
from backtest.setups import (Confluence, DEAD, FILLED, RESTING,        # noqa: E402
                             SetupSnapshot, WATCHING)
from notify import SIGNAL, send_telegram_id                            # noqa: E402

STRAT, SYM = "MpcSosFadeStrategy", "XAUUSD.p"


def snap(**kw) -> SetupSnapshot:
    base = dict(key="sample", strategy=STRAT, symbol=SYM, side=1, state=WATCHING)
    base.update(kw)
    return SetupSnapshot(**base)


def conf(arm: str, sos: bool, zone: str, zone_met: bool):
    return (Confluence("Arm", True, arm),
            Confluence("Shift of structure", sos, "confirmed"),
            Confluence("Retrace zone", zone_met, zone))


NOT_YET = "not tagged yet"
FVG_LIVE = "0.5-0.886 tagged, FVG live"
NO_FVG = "0.5-0.886 tagged, but no FVG in it"

# Each thread is (title, root_snapshot, [reply snapshots in order]).
# Between them these cover: both directions, all three zone wordings, 2-of-3 and 3-of-3, an order
# resting at 2 of 3, one blocking rule and three, a block that LIFTS, and all six ways a setup
# dies that the strategy has a sentence for.
THREADS = [
    ("1. The ordinary death — price never came back",
     snap(side=1, confluences=conf("swept Day Low", True, NOT_YET, False),
          zone=(3312.40, 3298.15), stop=3297.65),
     [snap(side=1, state=DEAD, confluences=conf("swept Day Low", True, NOT_YET, False),
           reason="Price never retraced into the 0.5-0.886 band, so the entry zone was never "
                  "reached. This is the ordinary way a setup dies.")]),

    ("2. Reached the zone, nothing to rest a limit on",
     snap(side=-1, confluences=conf("swept Week High", True, NOT_YET, False),
          zone=(3401.80, 3417.25), stop=3417.75),
     [snap(side=-1, state=DEAD, confluences=conf("swept Week High", True, NO_FVG, False),
           reason="Price DID reach the 0.5-0.886 band, but no fair-value gap overlapped it while "
                  "price was there — there was nothing to rest a limit on.")]),

    ("3. The one you want — forming, resting, filled",
     snap(side=1, confluences=conf("swept Prev Day Low", True, NOT_YET, False),
          zone=(3288.90, 3271.40), stop=3270.90),
     [snap(side=1, state=RESTING, confluences=conf("swept Prev Day Low", True, FVG_LIVE, True),
           zone=(3288.90, 3271.40), entry=3279.60, stop=3270.90,
           targets=(3296.10, 3311.75, 3334.20)),
      snap(side=1, state=FILLED, confluences=conf("swept Prev Day Low", True, FVG_LIVE, True))]),

    ("4. An order RESTING at 2 of 3 — the limit is real, price has not come to it",
     snap(side=-1, confluences=conf("swept Asia High", True, NOT_YET, False),
          zone=(3358.20, 3372.90), stop=3373.40),
     [snap(side=-1, state=RESTING, confluences=conf("swept Asia High", True, NOT_YET, False),
           zone=(3358.20, 3372.90), entry=3366.05, stop=3373.40,
           targets=(3351.30, 3338.60, 3320.15)),
      snap(side=-1, state=DEAD, confluences=conf("swept Asia High", True, NOT_YET, False),
           reason="All three confluences met and the limit rested — price never came back to "
                  "touch it.")]),

    ("5. Blocked by ONE of your rules, then died",
     snap(side=1, confluences=conf("RSI divergence", True, NOT_YET, False),
          zone=(3305.60, 3290.10), stop=3289.60),
     [snap(side=1, confluences=conf("RSI divergence", True, FVG_LIVE, True),
           blocked_by=("Divergence / extreme-RSI veto",)),
      snap(side=1, state=DEAD, confluences=conf("RSI divergence", True, FVG_LIVE, True),
           reason="All three confluences met. The divergence / extreme-RSI veto refused the "
                  "entry.")]),

    ("6. Blocked by THREE rules at once",
     snap(side=-1, confluences=conf("swept Day High", True, NOT_YET, False),
          zone=(3390.15, 3404.80), stop=3405.30),
     [snap(side=-1, confluences=conf("swept Day High", True, FVG_LIVE, True),
           blocked_by=("Divergence / extreme-RSI veto", "Final hour (16:00-18:00 New York)",
                       "HTF breakout / bias filter")),
      snap(side=-1, state=DEAD, confluences=conf("swept Day High", True, FVG_LIVE, True),
           reason="All three confluences met. The final-hour rule (16:00-18:00 New York) refused "
                  "the entry.")]),

    ("7. Blocked, the rule LIFTED, and it traded anyway",
     snap(side=1, confluences=conf("swept Prev Week Low", True, NOT_YET, False),
          zone=(3264.70, 3248.35), stop=3247.85),
     [snap(side=1, confluences=conf("swept Prev Week Low", True, FVG_LIVE, True),
           blocked_by=("HTF breakout / bias filter",)),
      snap(side=1, state=RESTING, confluences=conf("swept Prev Week Low", True, FVG_LIVE, True),
           zone=(3264.70, 3248.35), entry=3256.10, stop=3247.85,
           targets=(3273.40, 3287.90, 3309.55)),
      snap(side=1, state=FILLED, confluences=conf("swept Prev Week Low", True, FVG_LIVE, True))]),

    ("8. Refused by the higher-timeframe filter",
     snap(side=-1, confluences=conf("swept Session High", True, NOT_YET, False),
          zone=(3345.05, 3359.60), stop=3360.10),
     [snap(side=-1, state=DEAD, confluences=conf("swept Session High", True, FVG_LIVE, True),
           reason="All three confluences met. The HTF breakout / bias filter refused the "
                  "entry.")]),
]


def render(s: SetupSnapshot, is_root: bool) -> str:
    """Exactly the routing `SetupAlerts._handle` uses, so the sample cannot drift from the bot."""
    if is_root:
        return alerts.format_watching(s)
    if s.blocked_by:
        return alerts.format_blocked(s)
    if s.state == RESTING:
        return alerts.format_entry_zone(s)
    return alerts.format_resolved(s)


HEADER = ("🧪 EXAMPLES — none of these are live setups.\n"
          "Eight sample threads follow, one per shape a real setup can take. Every message is "
          "rendered by the same code the bot sends with. Delete this block when you are done.")
FOOTER = "🧪 End of examples. Everything after this line is real."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print, send nothing")
    args = ap.parse_args()

    def post(text, reply_to=None):
        if args.dry_run:
            print(("  └ " if reply_to else "") + text.replace("\n", "\n     ") + "\n")
            return 1
        mid = send_telegram_id(text, SIGNAL, reply_to=reply_to)
        time.sleep(1.2)                      # Telegram rate limit; keeps the thread order intact
        return mid

    post(HEADER)
    for title, root, replies in THREADS:
        if args.dry_run:
            print(f"\n=== {title} ===")
        rid = post(render(root, True))
        for r in replies:
            post(render(r, False), reply_to=rid)
    post(FOOTER)
    print(f"{'would send' if args.dry_run else 'sent'}: "
          f"{sum(1 + len(r) for _, _, r in THREADS) + 2} messages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
