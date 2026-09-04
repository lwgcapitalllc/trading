"""EXTREME LEG — the run INTO the shift of structure, not the fade after it.

Ported from `strategies/tradingview/extreme_leg_strategy.pine`. The SOS Fade bot waits for structure
to shift and then fades the retracement; this takes the move that CREATES the shift — from the
extreme up to the swing whose break IS the shift. Stop beyond the extreme, exit part of the way to
the swing, one position at a time.

    ExtremeLegConfig       — every Pine input, and nothing that is not one
    HtfStructure           — the 15-minute half, aggregated from the chart's own bars
    LegState               — what the Pine computed on a bar, whether or not it traded
    ExtremeLegExecution    — one slot, a frozen bracket, and the costs it paid
    ExtremeLegStrategy  — the driver

⚠ **NO PARITY GATE HAS RUN AGAINST THIS YET.** Stage 4 of `docs/STRATEGY_WORKFLOW.md` — a bar-by-
bar CSV off the export twin — is the one step no machine here can take, and until
`tools/compare_extreme_leg.py` exits 0 on one, every number this package produces is a lab finding
and not a measurement. Two known places the two sides may disagree are written down in
`strategy.py::_update_sweeps`; neither has been settled, and neither is guessed at in code.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from .config import ExtremeLegConfig
from .execution import Blocked, ExtremeLegExecution
from .htf import HtfStructure
from .strategy import LegState, ExtremeLegStrategy

__all__ = [
    "Blocked",
    "ExtremeLegConfig",
    "ExtremeLegExecution",
    "HtfStructure",
    "LAB_STRATEGY",
    "LegState",
    "ExtremeLegStrategy",
]

# ── Lab registration (runner="python") ───────────────────────────────────────────
# The scanner imports this package and reads this dict; the lab keys the strategy off the CLASS
# name, so it registers alongside the SOS Fade bot and the B-LEG rather than replacing either.
#
# ⚠ `suggested_instrument` is a suggestion; the 5-minute FRAME is not. See the strategy docstring —
# on a 15-minute frame the trigger and the target become the same series and there is no trade left
# to take. The lab cannot enforce a timeframe, so this is written where somebody reads it.
LAB_STRATEGY = {
    "name": "Extreme Leg",
    "config": ExtremeLegConfig,
    "strategy": ExtremeLegStrategy,
    "suggested_instrument": "XAUUSD",
    # 🔴 THE FRAME THIS BOT WAS MEASURED ON, in minutes — its Pine is exported from a 5-minute
    # chart and its gate is 21,328 M5 bars (CLAUDE.md, 2026-09-02).
    # ⚠ It is a DEFAULT the lab fills in, never a refusal: nothing here stops a run on
    #   another frame, so a figure quoted off one is a different experiment and has to say
    #   so. Before this key existed the stack page ran every leg on ONE frame the reader
    #   picked, so a 5m bot silently replayed on 15m beside a 15m one and the table read
    #   as a portfolio result.
    "suggested_bar_value": 5,
    "category": "reversal",
    "self_sizing": True,
    # 🔴 THIS BOT PRICES THE SPREAD AS A FLAT ROUND-TRIP CHARGE AND CANNOT MOVE THE FILL, so the
    # lab charges it the flat spread when costs are on instead of the bid/ask model every other
    # package gets. Without this the lab had no way to know: "costs ON" always resolved to moved
    # fills, `ExtremeLegExecution` refused that profile at construction, and the run died three
    # seconds in with a stack trace — i.e. THIS STRATEGY COULD NOT BE RUN CHARGED AT ALL while
    # the switch on the page said it could. Same three costs are billed either way; only the
    # spread's model differs, and the stored cost layers record which was used so a comparison
    # across the two refuses rather than reading the gap as the strategy's doing.
    # ⚠ It is a SECOND copy of what `execution.py` already enforces —
    # `tests/test_extreme_leg.py::test_the_declaration_matches_what_the_constructor_actually_does`
    # pins them together, because a declaration that drifts from its refusal gets a run charged a
    # model the code then rejects, which is the exact failure this key exists to remove.
    "supports_bid_ask_fills": False,
    # This bot's own word for its setup, worn by its trades on the price chart. Until 2026-09-02
    # that chip was hard-coded to the SOS Fade bot's word on EVERY strategy's chart, so these trades
    # carried another bot's label. ⚠ A LABEL and nothing else — no run, no cost and no decision
    # reads it, so changing it repaints chips and moves nothing. ⚠ Keep it SHORT: it is drawn in a
    # chip beside the entry price and a long word pushes the price off the marker.
    "chart_tag": "XLEG",
    # 🔴 **NO `display_under` — THIS ROW IS TOP LEVEL, AND THAT IS A DECISION (Aaron, 2026-09-02:
    # "move it to root").** It was listed under the SOS Fade bot until then, on the reasoning that the
    # suite is carved up by LEG off one structure stream and this is the leg BEFORE the one SOS Fade
    # trades. That reasoning is still true and it is still the wrong thing to draw as an indent:
    # **nesting reads as "child of", and this bot is a SIBLING, not a descendant.** It has its own
    # Pine source, its own parity gate, its own config, and it runs standalone, in any stack, on
    # any instrument. Measured over 6.6 years it holds ZERO same-side overlap with SOS Fade, correlates
    # +0.035 month to month, and on one shared account the two refuse each other essentially never.
    #
    # ⚠ **The indent was carrying two different relationships at one level, which is what made it
    # misread.** `loss_recovery` sits under SOS Fade too and genuinely CANNOT run without it — it arms
    # off that bot's closed losses and declares `requires_source`. A row that cannot exist alone
    # and a row that competes for the account as an equal were drawn identically.
    #
    # ⚠ **Do not re-add the field without saying why here.** Its failure mode is silent in both
    # directions: a dropped declaration and a typo'd parent both render at the top level, so
    # nothing on screen would show the decision had been reversed. `tests/` pins it.
}
