"""RealignConfig — the Realign bot's config.

A strict SUPERSET of `sos_fade`'s `SosFadeConfig`, for the same reason `BLegConfig` is:
this fork trades through the SAME exit ladder, sizing and cost machinery, and only the
ENTRY differs. Inheriting keeps the exit levers in lockstep.

🔴 **THE INHERITED DEFAULTS ARE THE RISK, NOT THE NEW FIELDS.** Every SOS Fade default this class
does not re-declare arrives uninvited — the `BosConfig` incident (2026-08-07), where two
SOS Fade defaults added in the preceding five days silently broke a new fork. The pins below are
the result of diffing this fork against the parent field by field, and each one records WHY.

⚠ The entry-side SOS Fade fields (`exec_fib_nearest`, `exec_deep_fib`, `exec_fvg_pre_zone`,
`exec_fib_overlap`, `exec_fib_deep_edge`, `exec_sl_deep`) are INERT here and are
deliberately left alone rather than pinned: this fork places no fib-priced order, so
nothing reads them. Pinning them would imply they mean something here.

See `docs/REALIGN_SPEC.md` for the setup and every measurement behind these defaults.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# strategies/python on path so `sos_fade` imports by bare name (the shim the tests use).
_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from sos_fade.config import SosFadeConfig  # noqa: E402


@dataclass(frozen=True)
class RealignConfig(SosFadeConfig):
    exec_min_atr_pct: float = 0.0   # pinned OFF, and INERT here — this fork overrides `_place_entries`
    """The parent's dead-market floor, pinned to the inert value.

    The parent turned it ON at 0.08 on 2026-08-26. It is enforced inside the parent's
    `_place_entries`, which this fork overrides, so it never runs on this path. Pinned so a
    parent default change cannot silently claim a filter this fork does not run.

    ⚠ It has never been swept here, and this fork has NO parity gate at all, so there is nothing
    that would catch it starting to bite. Do not read the pin as a measured choice for this setup.
    """

    # ── the setup ────────────────────────────────────────────────────────────────
    realign_htf_minutes: int = 15
    """The EXTERNAL frame, aggregated from the chart frame inside the strategy.

    The strategy runs on the 5m stream and builds its own 15m bars, which is what keeps it
    SINGLE-frame from the runner's point of view. A genuinely dual-frame strategy needs
    `run_dual`, and `backtest.optimizer.run_sweep` refuses those outright — it would be
    locked out of the optimizer, the sweeps and the stress test.
    """

    realign_window_hrs: float = 72.0
    """How long a setup stays armed after the external false break.

    72 since 2026-09-16 (Aaron's call; `realign_optimization.md` → Run 13). ⚠ Measured with the
    20-day momentum filter on: 24h 94 trades / +48.50R → 72h 115 / +69.32R, and **+19.2R of the
    +20.8R gain is ONE trade** (2023-09-25 short); the other 20 added trades net +1.6R. 72-120
    is a plateau only because every one of them contains that trade.
    """

    realign_pattern: str = "any"
    """Which internal sequence counts as the realignment.

    "any"      — a counter-direction internal break, then a with-trend internal SOS
    "opposing" — the two opposing internal SOS specifically
    "strict"   — with-trend iBOS, then counter iSOS, then with-trend iSOS

    🔴 **THE RANKING INVERTS WHEN COSTS ARE CHARGED, AND AN EARLIER NOTE HERE HAD IT
    FLATLY WRONG.** This docstring said `strict` was "the WORST of the three" and cited
    percentages that came from the TRIGGER SCAN — the one thing the note below
    `realign_long_source` says must never decide an exit-sensitive question. Measured by
    REPLAY instead, 467,352 M5 bars 2020-01-02 -> 2026-08-06:

        FREE                trades   total R    avg R    win     PF     maxDD
          any                 162    +45.14R   +0.279   44.4%   1.658   12.15R
          opposing             43    +11.36R   +0.264   48.8%   1.832    4.58R
          strict               42    +12.36R   +0.294   50.0%   1.977    4.15R

        CHARGED (puprime_standard)
          any                 162    +35.81R   +0.221   33.3%   1.496   15.52R
          opposing             43     +6.22R   +0.145   30.2%   1.425    5.51R
          strict               42     +7.33R   +0.175   31.0%   1.540    4.41R

    **Free, `strict` is the BEST of the three on avg R, profit factor AND drawdown.**
    Charged, it is not: costs take 40% of its average R (+0.294 -> +0.175) against `any`'s
    21% (+0.279 -> +0.221), and the order flips.

    ⚠ **The mechanism is NOT measured.** The obvious candidate is that the strict
    sequence's stops are tighter, so a fixed spread costs more R — plausible, cheap to
    check (median stop distance per pattern) and deliberately NOT asserted here.

    **`any` still ships**, on the two figures that survive charging: 5x the total R
    (+35.81R vs +7.33R) and more R per unit of drawdown (2.31 vs 1.66). But the sequence
    Aaron drew is a REAL rule with the best per-trade quality in the book, not a filter
    that "carries no information" — which is what the old note claimed and what would have
    stopped anyone looking at it again.
    """

    realign_long_source: str = "swing"
    realign_short_source: str = "swing"
    """WHICH STRUCTURE STREAM EACH SIDE TRIGGERS ON — and they genuinely differ.

    🔴 **BOTH SIDES WANT "swing", AND THE TRIGGER SCAN SAID OTHERWISE.** Measured by real
    replay through the full exit ladder, 2020-01-02 -> 2026-08-06, shorts alone:

      SHORT on "swing"     87 trades   +20.22R   avg +0.232R   maxDD  6.39R
      SHORT on "internal"  60 trades   -13.26R   avg -0.221R   maxDD 14.61R

    ⚠ The standalone TRIGGER scan (`backtest/tools/internal_realign_scan.py`) reported the
    OPPOSITE for shorts — "internal" at +9.6% over control (+2.1σ) against a 4R target.
    That scan scores every setup independently at a FIXED target, with no exit ladder, no
    staged stop and no position slot. Its short edge was entirely in the tail (+0.1σ at 1R,
    +2.1σ at 4R), and the real ladder banks at the structural target, so the edge it
    measured is one this strategy never collects. **A trigger prior is not a strategy
    result, and here the two disagree in SIGN.** Keep the scan for counting setups; take
    the direction of any exit-sensitive question from a replay.

    ⚠ "swing" is the frame's EXTERNAL stream, which is the internal structure OF THE 15m.
    It is not the engine's `InternalEvents`, which is the sub-structure of the 5m itself,
    one level further down than a chart draws.
    """

    realign_entry_mode: str = "market"
    """WHEN the order goes in once the realignment has fired.

    "market" — at the close of the bar the realignment confirmed on. What every realign
               figure measured before 2026-09-15 used, and what the Pine twin does.
    "retest"  — rest a LIMIT at the level the realignment broke and wait for price to come
               back to it. Aaron's brother's actual trades, relayed 2026-09-15:
               *"price retests that shift of structure area and then goes ... if we get it
               on the retest that's even better"*.

    🔴 **THIS IS THE ONE STRUCTURAL ANSWER TO THIS FORK'S COST PROBLEM, WHICH IS WHY IT IS
    BUILT BEFORE ANY OTHER IDEA ON THE LIST.** A market entry pays the spread on the way in;
    `execution.py`'s header records that this is the ONE thing that does not transfer from
    SOS Fade, whose limit entries avoid it. Charging costs takes 21% of this book's average R
    at the shipped pattern and 40% at `strict`, and the mechanism was never measured. A
    resting limit removes the entry-side charge AND enters nearer the stop, so the same
    structural target is a larger multiple of a smaller R.

    ⚠ It also introduces the fill uncertainty a market entry does not have — a limit that is
    never touched is a trade that never happens, and the jitter audit found exactly that
    dominates SOS Fade's trade-list stability. Expect a SMALLER book, and judge the two on
    total R and drawdown rather than on trade count.

    ⚠ Measured in `realign_optimization.md`: on the 5m trail it beat market on every axis (Run
    2); on the 15m trail — today's default — it is better per trade but WORSE in total, drawdown
    and without its best trade (Run 10), so "market" stays. The Pine has it and its parity is
    green (Run 9).
    """

    realign_retest_at: str = "level"
    """WHERE the retest limit rests. Read only when the entry mode is "retest".

    "level" — the structure level the realignment broke, from the tracker. Aaron's own
              description, and the only one of the two that names a price the market itself
              marked. ⚠ The engine cannot always attribute a break to a stored swing, and a
              setup with no level is REFUSED rather than quietly entered at market — see
              `RealignState.trigger_level`.
    "mid"   — halfway between the stop anchor and the confirming close. Always available, so
              it keeps the book comparable with the market row; use it to tell "the retest
              idea works" apart from "the level lookup dropped the bad trades".

    Neither is a default anyone has measured. They exist so the question is answered by two
    independent prices rather than one, because a single retest price that wins is
    indistinguishable from a lucky offset.
    """

    realign_retest_bars: int = 12
    """How many chart bars the retest limit rests before it is cancelled. Chosen, not measured.

    🔴 **AN EXPIRY IS NOT OPTIONAL HERE, AND ITS ABSENCE WOULD BE A SILENT LOOKAHEAD-SHAPED
    BUG.** The parent re-places its resting order every bar off a live setup, so a stale one
    cannot survive. This fork places ONCE, on the trigger bar, so an order with no expiry
    rests until something fills it — which could be days later, at a price whose structure
    has been gone for a week, and the trade would be booked against a target and stop frozen
    in a market that no longer exists. 12 bars is one hour on the 5m frame.

    ⚠ The order is ALSO cancelled if price reaches the stop first: the setup is invalidated
    before it was ever entered, and filling after that books a trade the rule refuses.
    """

    realign_tp_r: Optional[float] = None
    """Close the WHOLE trade at this multiple of its own risk. `None` = the structural ladder.

    Aaron, 2026-09-15: *"I like to have an average take profit that I could just close the
    trades off of and bank the money. That way I'm not holding over days or sessions."*

    The complaint it answers is real and measured: at the retest entry over 2020-01 → 2025-08,
    **every one of the 97 trades exits on a trailing stop or the 36-hour time stop — nothing
    ever banks at a target** (`exec_tp1_pct` and `exec_tp2_pct` are both 0.0, so the two rungs
    only STAGE the stop). Median hold 11.2h, but **28 of 97 run past 24 hours and the longest
    is 209 hours (8.7 days)**.

    🔴 **THIS CAPS THE TAIL, AND THE TAIL IS WHERE THIS STRATEGY'S MONEY IS.** Same 97 trades,
    how far they ever ran: median 0.73R, and only 43% / 27% / 18% ever reach 1R / 2R / 3R —
    against a best of **24.6R**. A fixed target sells the 24.6R trade at N and keeps every
    loser whole. ⚠ It does NOT follow that a fixed target must lose: closing earlier FREES THE
    POSITION SLOT, and a strategy with one slot takes a different, later set of trades as a
    result. That effect is the one that got the minimum-stop guard's SIGN wrong (+1.84R
    estimated from a finished trade list, −1.84R when actually replayed). **Measure this by
    REPLAY. Never by recomputing R off a trade list's excursions.**

    ⚠ It re-prices the FIRST rung and requires `exec_tp1_pct = 100` so the trade actually
    closes there — refused otherwise rather than silently half-banking into a ladder whose
    remaining stages were priced off a structural target that is no longer the target.
    """

    realign_flat_before_weekend: bool = False
    """Close any open trade `flat_by_close_min` before the FRIDAY close (gold 17:00 New York).

    Aaron, 2026-09-15: *"what if we don't hold to weekends? ... fifteen minutes before the
    market close, we close the trade."*

    The parent already has the DAILY version (`flat_by_close`, off) and the New-York-hour
    plumbing behind it, including DST — `_in_flat_window` is reused here rather than
    re-derived, so the two rules cannot drift into two opinions about when the close is.
    This one differs from it in exactly one way: it fires on Friday only.

    ⚠ The weekday is read off the UTC timestamp, which is correct HERE and would not be in
    general: 16:45 New York on a Friday is 20:45 or 21:45 UTC depending on DST, and both are
    still Friday. A window closer to midnight NY would need the converted date.

    ⚠ The close is a MARKET order filled at the next bar's open, the same one-bar delay every
    other exit here uses. On the last bar of the week there IS no next bar, so the position is
    carried to the Sunday open instead — which is the one case this rule exists to prevent.
    `flat_by_close_min` must therefore stay comfortably larger than one bar. Measured at the
    shipped 15 minutes on the 5m frame (3 bars of room), and NOT measured at any other value.

    ⚠ **Off, and it costs money on the 15m trail** (Run 10): 139 trades +40.36R against +49.49R
    without it, and a DEEPER drawdown (17.45R vs 11.38R). It was free on the 5m trail.
    """

    realign_trail_frame: str = "external"
    """WHICH FRAME'S CONFIRMED SWINGS THE RUNNER TRAIL ANCHORS ON. **"external" — the 15m.**

    🔴🔴 **SHIPPED "chart" UNTIL THE EVENING OF 2026-09-16, AND THE ONE NUMBER HOLDING IT THERE WAS
    A BUG.** The first parity export showed this port's external anchor was `None` on every bar
    it had ever replayed (`htf.py` read a field the event record does not carry), so the
    "−15.68R on the external frame" below measured a trail with NO structure anchor. Fixed and
    re-measured, 2020-01-02 → 2026-08-06, `puprime_standard`:

        chart      162 trades  +36.17R  avg +0.223  PF 1.50  maxDD 15.36R  halves  +8.51 / +27.66
        external   161 trades  +56.25R  avg +0.349  PF 1.78  maxDD 11.38R  halves  +9.56 / +46.69

    The default moved because the 15m is the DESIGN — Aaron's call, recorded in
    `strategies/tradingview/docs/realign_strategy.md` [10]: enter off the 5m, ride the 15m — and
    the file he trades has always run it. "chart" was never chosen; the port was written against
    a wrong comment. ⚠ **The table is NOT the reason, and it is not a clean test**: the window has
    been used for every pick in this package. It is evidence the design was not a mistake.
    ⚠ **Runs 2-6 used the 5m trail; Run 10 re-checked them on this default** and three did not
    survive — the retest "beating market", the 12-hour clock and the flat rules. The random
    control strengthened (z +3.58).

    The history of how the two sides came apart, kept because it is the transferable part:

    🔴 **FOUND 2026-09-16, BEFORE THE PARITY GATE EXISTED, AND IT IS A REAL DIVERGENCE.**
    `realign_strategy.pine` anchors on `hConfLo` / `hConfHi`, which come out of its
    `request.security` call on the EXTERNAL frame — 15m swings. This Python inherits SOS Fade's
    `_trail_swing_lo = sig.last_conf_low`, where `sig` is the CHART frame — 5m swings.
    **Every Realign figure in this repo was measured on the 5m anchor; the file Aaron reads on
    a chart trails the 15m one.**

    ⚠ **The Pine's own comment on that line says "the chart frame's last CONFIRMED swing",
    which is what the Python does and NOT what the Pine does.** The comment contradicts the
    code beside it, and that is almost certainly how the two diverged — the port was written
    against the comment. `strategies/tradingview/CLAUDE.md` had the code right the whole time.

    **Why it is not cosmetic.** This strategy has no take-profit: every trade exits on the
    trail, the time stop or the flat-by-close, so the trail IS the exit. A 15m anchor sits
    further from price than a 5m one, so the Pine's trail is LOOSER — it gives runners more
    room and hands back more on a reversal. It is also a live candidate for the undiagnosed
    drawdown disagreement (Strategy Tester 17.79% against 15.52R here), which has been open
    since the Pine was first run.

    ⚠ The morning's reasoning for keeping "chart" read: *a decision to keep the record stable, NOT
    a finding that the chart frame is correct.* The gate settled it the same day.
    """

    realign_longs: bool = True
    realign_shorts: bool = True

    realign_sl_buf_tk: int = 20
    """Ticks beyond the internal leg extreme the stop sits."""

    realign_min_rr: Optional[float] = None
    """Refuse a setup whose reward-to-risk at ENTRY is below this. `None` = no filter.

    The stop is the counter-move extreme and the target is the pre-deviation external
    high. **Those two are set independently, so R:R varies enormously per trade and is
    KNOWN AT ENTRY** — which is what makes it a filter rather than a hindsight
    observation. Measured over the 162-trade book: min **-3.68**, median 1.69, max 14.92.

    🔴 **`None` IS NOT THE SAME AS 0.0, AND THE DIFFERENCE IS A PINE PARITY DEFECT.**
    `realign_strategy.pine` guards its entry with `tgtLong > close` (and the short
    mirror); **this Python has never had that check**, so it takes trades whose target is
    already BEHIND the entry — 7 of 162, R:R down to -3.68. Those trades are not junk:
    TP2 is satisfied on the entry bar, the ladder jumps to stage 2 and they run as pure
    trailing trades, making **+5.67R between them (+0.81R average, against the book's
    +0.221)**. So the Pine is refusing the better-performing tail of its own book.
    **Which side is right is NOT settled here** — `0.0` reproduces the Pine, `None`
    reproduces every Python figure measured before 2026-08-13, and the parity gate is what
    decides. Default stays `None` so no historical number moves.

    ⚠ Any positive value is a NEW filter that neither implementation has. Measure it by
    REPLAY, never by dropping rows from a finished trade list: with one position slot a
    refused setup FREES the slot and a different setup takes it, which is how the
    minimum-stop guard's cheap estimate got its SIGN wrong (+1.84R estimated, -1.84R
    replayed).
    """

    realign_trend_minutes: Optional[int] = None
    """Refuse a trade against the structure direction of THIS slower frame. `None` = off.

    🔴 **THE PROFITABLE DIRECTION FLIPS WITH GOLD'S OWN TREND, AND THAT IS THE ONE
    STRUCTURAL FINDING IN THIS STRATEGY'S DATA.** Split the 162-trade book in half:

        2020-01 -> 2023-04   shorts +17.18R (43 tr)   longs  -8.83R (39 tr)
        2023-05 -> 2026-08   shorts  +2.90R (42 tr)   longs +24.55R (38 tr)

    Gold over those halves: roughly flat-to-down through 2021 (-4.2%) and 2022 (-0.3%),
    then +12.9% / +27.1% / +64.5% through 2023-2025. **The side that makes money is the
    side aligned with the prevailing move, and it reverses when the move does.**

    The mechanism is the setup's own logic rather than a pattern in a table: a false break
    is a liquidity grab AGAINST a prevailing direction, and the realignment is the
    resumption. Taken against the dominant trend, the same shape is a genuine reversal
    being faded — which is a different trade with a different expectancy.

    ⚠ **THIS HYPOTHESIS WAS DERIVED FROM THE SAME 162 TRADES IT WOULD BE TESTED ON, AND
    THAT IS EXACTLY HOW A SECOND OVERFIT HAPPENS AFTER THE FIRST ONE IS CAUGHT.**
    `realign_min_rr` looked excellent on the full history and was then shown to be a fit to
    one half. Any value here must clear the same bar: it has to help in BOTH halves
    separately, not in the total. Default is `None` until it does.
    """

    realign_mom_days: Optional[int] = 20
    """Refuse a trade pointing the SAME way as gold's move over this many trading days. `None` = off.

    The move is the sign of the last completed day's close against the close N days before it
    (`strategies/python/daily_momentum.py`, days rolling at 17:00 New York). A trade AGAINST the
    move, or on a day with no move, is kept. **Fewer than N + 1 completed days REFUSES** — the
    same unknown-is-not-a-pass rule as the trend gate above. Pine: "Skip trades with the N-day
    move" (0 = off); refusal code 7.

    MEASURED 2026-09-16 (`realign_optimization.md` → Run 12): at 20 days the worst drawdown fell
    14.48R → 5.07R and total R 54.09 → 48.50, with the recent half 18R WORSE. It fails the
    both-halves bar; Aaron chose it anyway ("I like steady better"). **ON at 20 since
    2026-09-16**, after its TradingView export (filter at 20, 8 setups refused) passed the parity
    gate. 🔴 Every realign figure before that date was measured with it OFF — pass `None` to
    reproduce one.
    """

    # ── inherited defaults this fork must REFUSE ─────────────────────────────────
    exec_secondary: bool = False
    """PINNED OFF — the 1-minute re-entry needs a second bar stream through `run_dual`.

    The parent defaults this **True** (2026-08-07). Inherited, every replay of this fork
    would either refuse outright or — worse, on the paths that do not check — return a
    primary-only book while reporting itself as having re-entries. Same call `b_leg`
    makes, for the same reason.
    """

    exec_scale_in: bool = False
    """PINNED OFF — adding to a winner. The parent defaulted it True on 2026-09-06 (Aaron's
    call, named for SOS Fade), and `realign_strategy.pine` has no scale-in input or code.

    MEASURED 2026-09-10 (Vantage 5m, 2020-01-02 → 2026-08-06, same 162 trades either way): the
    inherited adds lifted this book +35.81R → +49.29R charged. That is a CANDIDATE, not a
    result — nobody chose it for this setup and no chart can confirm it. Turn it on only in a
    run that says so, and only after this bot has a parity gate.
    """

    exec_runner_trail: str = "Structure (swing)"
    """PINNED here, no longer inherited: the runner trails the external frame's confirmed swing
    with no % ratchet (Aaron's call, 2026-09-16; `realign_optimization.md` → Run 13).

    ⚠ The parent's "Structure + % ratchet" at 1% touched only 5 trades in 2020-2026, and
    **+18.1R of the +19.4R difference is ONE trade** (2020-11-09: +18.5R ratcheted, +36.6R here).
    Worst drawdown is unchanged. It gives back more on a reversal in exchange for that tail.
    """

    exec_risk_pct: float = 10.0
    """PINNED at the value this fork has always run. The parent defaulted it 10.0 → 5.0 on
    2026-09-13 to match SOS Fade's live share; every realign figure was measured at 10.

    ⚠ `realign_strategy.pine` ships 1.0 ("R is scale-free"), so the two sides already differ
    here. That is for this bot's parity gate to settle, not for a parent's default to move.
    """

    def __post_init__(self) -> None:  # type: ignore[override]
        parent = getattr(super(), "__post_init__", None)
        if parent is not None:
            parent()
        if self.realign_trail_frame not in ("chart", "external"):
            raise ValueError(f"realign_trail_frame must be chart|external, "
                             f"got {self.realign_trail_frame!r}")
        if self.realign_entry_mode not in ("market", "retest"):
            raise ValueError(f"realign_entry_mode must be market|retest, "
                             f"got {self.realign_entry_mode!r}")
        if self.realign_retest_at not in ("level", "mid"):
            raise ValueError(f"realign_retest_at must be level|mid, "
                             f"got {self.realign_retest_at!r}")
        if self.realign_retest_bars <= 0:
            # A zero or negative expiry is not "rest forever", it is an order cancelled
            # before it can fill — a retest row that silently takes no trades at all.
            raise ValueError(
                f"realign_retest_bars must be > 0, got {self.realign_retest_bars!r}")
        if self.realign_tp_r is not None:
            if self.realign_tp_r <= 0:
                raise ValueError(
                    f"realign_tp_r must be > 0 or None, got {self.realign_tp_r!r}")
            if self.exec_tp1_pct != 100.0:
                # Banking less than everything at a fixed-R rung leaves a remainder running
                # against stages that were priced off the structural target this lever just
                # replaced — a ladder describing a trade plan nobody chose.
                raise ValueError(
                    f"realign_tp_r needs exec_tp1_pct=100 so the trade actually closes at the "
                    f"target; got exec_tp1_pct={self.exec_tp1_pct!r}")
        if self.realign_pattern not in ("any", "opposing", "strict"):
            raise ValueError(f"realign_pattern must be any|opposing|strict, "
                             f"got {self.realign_pattern!r}")
        for name in ("realign_long_source", "realign_short_source"):
            val = getattr(self, name)
            if val not in ("swing", "internal"):
                raise ValueError(f"{name} must be swing|internal, got {val!r}")
        if self.realign_window_hrs <= 0:
            raise ValueError("realign_window_hrs must be > 0")
        if self.realign_trend_minutes is not None and self.realign_trend_minutes <= self.realign_htf_minutes:
            # A "trend" frame at or below the frame the false break is read on is not a
            # slower context, it is the same read under another name — and it would pass
            # silently while filtering on something the setup already knows.
            raise ValueError(
                f"realign_trend_minutes ({self.realign_trend_minutes}) must be SLOWER than "
                f"realign_htf_minutes ({self.realign_htf_minutes})")
        if self.realign_mom_days is not None and self.realign_mom_days < 1:
            # 0 is the Pine's "off"; here off is None. Accepting 0 would state a filter that
            # cannot run — refuse, so a copied Pine value cannot land as a silent no-op.
            raise ValueError(
                f"realign_mom_days must be >= 1 or None, got {self.realign_mom_days!r}")
        if self.realign_min_rr is not None and self.realign_min_rr < 0:
            # A negative floor is indistinguishable from `None` in effect but states
            # something false — that a minimum was chosen. Refuse rather than accept it.
            raise ValueError(
                f"realign_min_rr must be >= 0 or None, got {self.realign_min_rr!r}")
        if self.exec_secondary:
            # Refuse rather than silently produce a primary-only book — the distinction
            # this repo has been bitten by twice.
            raise ValueError(
                "realign has no 1m secondary re-entry; exec_secondary must stay False")
        if 60 % self.realign_htf_minutes and self.realign_htf_minutes % 60:
            raise ValueError("realign_htf_minutes must divide or be a multiple of an hour")
