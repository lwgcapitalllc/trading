"""gate_common.py — the rules every Pine↔Python parity gate needs and none of them owns alone.

🔴 WHY THIS MODULE EXISTS AT ALL, given eleven previously-standalone tools.
The live-final-bar rule below was written THREE times before it was written once: `compare_bos.py`
had it, `compare_candles.py` copied it with a comment saying so, and a third copy was about to be
added to `compare_fvg.py` on 2026-09-10. Eleven copies of a three-line rule is the same disease
this repo already pays for in Pine, where there is no import to prevent it — here there is one, so
not using it would be a choice.

⚠ Deliberately NARROW. This is not a parity-gate framework and must not become one: each engine's
comparison is genuinely its own, and a shared base class would be the over-engineering that this
repo counts as a corner cut in its own right. What lives here is a fact about the EXPORT FORMAT,
which is the one thing all eleven demonstrably share.

Standard library only. Import it the way the gates already import their engine — `engines/` is on
sys.path by the time this is reached.
"""

from __future__ import annotations


def drop_live_final_bar(rows, *, quiet=False):
    """Drop the export's last row, which is TradingView's still-forming LIVE bar.

    🔴 THE LIVE BAR IS NOT A CLOSED BAR AND EVERY GATE WAS FEEDING IT AS ONE. Most Pine blocks gate
    their detection on `barstate.isconfirmed`, so on that bar they do not run — while the CSV row
    carries the bar's CURRENT open/high/low/close. Hand that to a Python engine, which has no
    concept of an unconfirmed bar, and it forms events Pine never had. The mismatch is a defect in
    the COMPARISON, not in either implementation, and it lands on the one bar a reader is least able
    to explain.

    ⚠ MEASURED 2026-09-10: it fired on the fair-value-gap gate (one bar in 20,188, both harnesses,
    identically) and ALL TWELVE committed golden exports end on a row carrying values, so every gate
    in this repo carried the exposure. They were green because their last bar happened to form and
    mitigate nothing. **A bug that has never fired is not absent, it is unobserved**, and one bar in
    twenty thousand is exactly the hit rate that keeps it that way.

    ⚠ It is NOT decided from the clock. "Is this bar still open?" is a question about when the export
    was TAKEN, not about when the gate is RUN — a committed golden export would answer it wrong for
    ever, and would start answering it wrong the day after it was taken. The final row is treated as
    suspect unconditionally instead: it costs one bar out of twenty thousand and it cannot rot.

    ⚠ It is NOT the same rule as `_drop_forming_tail` in `compare_candles.py` / `compare_bos.py`,
    and both are needed. That one trims a TRAILING RUN of rows whose plotted columns are all blank —
    which is what a live bar looks like when the harness plots per-bar PULSES. A harness that plots
    ARRAY STATE (the gap list, the level list) has values on the live bar and is invisible to it.
    Measured on the golden set: the blank-run test finds nothing on any of the twelve, including the
    candlestick export whose own tool carries it.
    """
    if len(rows) <= 1:
        return rows
    if not quiet:
        # ⚠ "note:", NOT "⚠". scripts/check_engine_gates.py echoes 🔴/⚠ lines under a passing tick
        # because those are caveats about that particular run - a coverage hole, a branch neither
        # side entered. This line is a constant of the export FORMAT and would print identically on
        # all twelve, which is precisely how a reader learns to skip the marker that matters.
        print(
            "note: dropped the final row - TradingView's last bar is live and unconfirmed, so the "
            "Pine block's `barstate.isconfirmed` detection never ran on it."
        )
    return rows[:-1]
