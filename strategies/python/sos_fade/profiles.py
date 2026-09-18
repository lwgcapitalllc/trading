"""Named parameter sets for the SOS Fade strategy — one strategy, many instruments.

WHY THIS MODULE EXISTS
----------------------
`config.py`'s defaults are the GOLD configuration: 39 of its fields were moved to their
current values by measurements taken on XAUUSD. That is correct for the shipped bot and
those defaults must not move — every documented run, the Pine parity gate and both live
bots reproduce off them.

But the same defaults are the wrong starting point for a DIFFERENT instrument, because
they encode gold's volatility, spread and session behaviour. This module holds the
overrides that turn the shipped config into a named starting point for another market,
without editing a single shipped default.

THE SEAM IS GENERIC, THE PROFILES ARE CONCRETE
----------------------------------------------
`InstrumentFacts` carries what the SYMBOL is. `Profile` pairs those facts with a set of
strategy overrides. Any strategy in this repo with a frozen config dataclass can reuse
the same shape; nothing here is SOS-Fade-specific except the override dicts themselves.

WHAT A PROFILE IS NOT
---------------------
A profile is a STARTING POINT for a fit, never a validated configuration. `UNTUNED`
below has never been measured on anything. It exists so a new instrument can be fitted
from a defensible baseline instead of from gold's answers. Do not deploy it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from .config import SosFadeConfig


@dataclass(frozen=True)
class InstrumentFacts:
    """What the traded symbol IS — never a tuning choice.

    Every field here must be READ off the broker's own symbol info, never assumed.
    `mintick` and `point_value` decide position size, and rule 15 in the root CLAUDE.md
    was written about a 54.82-lot order caused by exactly this class of mistake.
    """

    symbol: str                 # the broker's own symbol string, suffix included
    mintick: float              # one price tick, from the broker's symbol info
    point_value: float          # cash value of 1.0 of price, PER UNIT (not per lot)
    daily_close_hour_ny: int    # the venue's daily rollover hour, New York time
    account_profile: str        # key into backtest.fills.PROFILES — MEASURED costs only
    bar_minutes: int            # the frame this instrument's profile is fitted on


@dataclass(frozen=True)
class Profile:
    """A named instrument + a set of strategy overrides on the shipped defaults."""

    name: str
    facts: InstrumentFacts
    overrides: Mapping[str, Any]
    status: str                 # "LIVE", "FITTING" or "UNMEASURED" — read before trusting
    note: str = ""

    def build(self) -> SosFadeConfig:
        """Return the config this profile describes.

        Instrument facts are applied LAST so an override dict can never silently
        contradict the symbol it is being run against.
        """
        cfg = replace(SosFadeConfig(), **dict(self.overrides))
        return replace(
            cfg,
            symbol=self.facts.symbol,
            mintick=self.facts.mintick,
            point_value=self.facts.point_value,
            daily_close_hour_ny=self.facts.daily_close_hour_ny,
            account_profile=self.facts.account_profile,
        )


# ── The instrument facts ──────────────────────────────────────────────────────────
# XAUUSD's are the values `config.py` already ships, restated here so a profile never
# depends on what the shipped defaults happen to be.
XAUUSD_VANTAGE = InstrumentFacts(
    symbol="XAUUSD",
    mintick=0.01,
    point_value=1.0,
    daily_close_hour_ny=17,
    account_profile="vantage_demo",
    bar_minutes=15,
)

# GBPJPY — MEASURED 2026-09-17 off PU Prime demo 700152905 (C:\\MT5_Demo), symbol GBPJPY.p.
#   Spec read: digits 3, point 0.001, contract 100,000, volume 0.01-100, broker minimum stop 0.
#   Spread: median 0.015 (15 points) over 956,001 STORED TICKS across 3 days, flat in every
#   session except the 21:00 UTC rollover hour, where the median is 0.19 and p99 is 0.31.
#   ⚠ A 120-SECOND LIVE SAMPLE READ 0.18 — 18x the real median — because it landed in that
#   rollover band. The snapshot is not the spread; this is why the stored-tick pass exists.
#   History: real bars on M15 and M5 back to AT LEAST 2000-01-01, which is where the probe
#   STOPS LOOKING. "At least" is the honest word — the probe returned its own search bound,
#   not a measured edge, and `backtest/data/history.py` currently words that result as though
#   it had measured one.
#
# 🔴 TWO THINGS HERE DO NOT BEHAVE LIKE GOLD AND BOTH CHANGE THE STRATEGY.
#   1. SWAP IS SEVERELY ASYMMETRIC: long +4.83, short -20.68 per lot per night. A long is PAID
#      to hold; a short bleeds. Those are POINTS, not dollars: converted they are +$3.10 and
#      -$13.25 per lot per night, so at a ~4-day median hold a short pays about $53/lot against
#      a long earning about $12. Gold's short swap is a credit, so a cost intuition carried over
#      from gold is not just wrong here, it is wrong with the sign flipped.
#   🔴 AND NOTHING IN `backtest/fills.py` DOES THAT CONVERSION. `SwapModel.per_lot_per_night`
#      returns the SYMBOL'S QUOTE CURRENCY while calling itself account-currency — always the
#      same thing until now, because every instrument here is USD-quoted. On this pair it would
#      overstate swap by 156x and refuse nothing. Fix it at the seam, for every non-USD-quoted
#      instrument at once, before pricing any of them. See notes/instrument_profiles.md.
#   2. POINT VALUE IS NOT CONSTANT. Gold's 1.0 of price is always $1.00. Here it is
#      yen-denominated, so it moves with USDJPY: `tick_value` read 0.6409188 per 0.001 tick on
#      2026-09-17, i.e. ~640.92 per 1.0 of price per lot AT THAT MOMENT. The figure below is a
#      SNAPSHOT, not a constant. ⚠ OPEN: a backtest spanning years cannot hold it fixed without
#      mis-sizing every trade far from that rate — decide how the runner sources it before any
#      result is believed. This is rule 15 territory.
GBPJPY_PUPRIME = InstrumentFacts(
    symbol="GBPJPY.p",
    mintick=0.001,
    # 🔴 PER UNIT, NOT PER LOT. `config.py` defines this as "1.0 of price = 1 unit", and gold's
    #   1.0 is per OUNCE, not per 100-oz lot. Read the broker's tick value and divide by BOTH the
    #   tick size AND the contract size: 0.6409188 / (0.001 * 100,000) = 0.006409188. An earlier
    #   draft of this file wrote 640.92, the per-LOT figure — 100,000x too large, and in a field
    #   that multiplies straight into risk. Rule 15, in the file that was warning about rule 15.
    point_value=0.006409188,   # ⚠ SNAPSHOT 2026-09-17, moves with USDJPY — see the note above
    daily_close_hour_ny=17,
    # ✅ MEASURED AND LIVE since 2026-09-17. This key pointed at a deliberately nonexistent
    #   profile until commission was read off a real filled round trip (2 deals, 0.02 lots,
    #   -$0.02 on demo 700152905) — commission lands on a DEAL and never on a symbol
    #   specification, so a trade was the only way to read it. Spread and swap were measured the
    #   same day. See `backtest/fills.py` → `puprime_ecn_gbpjpy`.
    account_profile="puprime_ecn_gbpjpy",
    bar_minutes=15,
)

# GBPUSD — MEASURED 2026-09-17 off PU Prime demo 700152905, symbol GBPUSD.p.
#   digits 5, point 0.00001, contract 100,000, volume 0.01-100, broker minimum stop 0.
#   Spread 0.00004 (0.4 pip) over 562,362 stored ticks, FLAT in every hour including the rollover.
#   Swap -1.03 long / -1.14 short: BOTH SIDES PAY, unlike gold and unlike GBPJPY.
#   Real M15 and M5 bars back to at least 2000-01-01 (a probe BOUND, not a measured edge).
# ✅ **USD-QUOTED, so `point_value` is 1.0 EXACTLY and no rate conversion applies** — tick value
#   1.0 / (tick size 0.00001 * contract 100,000). This is the simple case: contrast GBPJPY above,
#   where the same field is 1/USDJPY and moves with the market.
GBPUSD_PUPRIME = InstrumentFacts(
    symbol="GBPUSD.p",
    mintick=0.00001,
    point_value=1.0,
    daily_close_hour_ny=17,
    account_profile="puprime_ecn_gbpusd",
    bar_minutes=15,
)

# ⚠ Any FURTHER instrument has no InstrumentFacts here ON PURPOSE.
#   Nobody has read its symbol info off a broker, and `backtest/fills.py` carries no
#   cost profile for it. Writing plausible numbers here
#   would be rule 4 exactly: a guess in a doc that sends the next reader away from the
#   one-command check. Build its facts from a real symbol read and a measured spread/swap
#   profile, the way GBPJPY's above were built.


# ── GOLD — the shipped configuration, stated as a profile ─────────────────────────
# Deliberately EMPTY overrides. This profile exists so "what the live bots run" is a
# named thing rather than an implicit one, and so a diff against any other profile is
# a diff against something explicit. If this ever needs a non-empty override dict, the
# shipped defaults and the live bots have drifted apart and that is the bug.
GOLD = Profile(
    name="XAUUSD — shipped",
    facts=XAUUSD_VANTAGE,
    overrides={},
    status="LIVE",
    note="The measured gold configuration. Reproduces every documented run.",
)


# ── UNTUNED — the baseline for fitting a new instrument ───────────────────────────
# Aaron's ask, 2026-09-17: the strategy with the gold-specific tuning taken back off,
# as the starting point for a GBPJPY fit.
#
# 🔴 WHAT THIS IS AND IS NOT. Of the 39 gold-fitted fields, only 18 have a recoverable
# pre-tuning value; the other 21 were BORN TUNED — introduced by an optimisation commit,
# never having had an untuned state. None of those 21 is set here to a made-up number.
# They go INERT instead, because the four features that own 20 of them are switched off
# below. The one that would have stayed live, the time stop, is switched off on the
# ground that the feature did not exist at the original port, so absent IS its untuned
# state.
#
# ⚠ NEVER MEASURED, ON ANY INSTRUMENT. No run, no gate, no parity export. It is a
#   defensible place to START a walk-forward fit and nothing more.
UNTUNED = Profile(
    name="Untuned baseline",
    facts=XAUUSD_VANTAGE,   # replaced per instrument at fit time
    status="UNMEASURED",
    note=(
        "Gold tuning reverted where a pre-tuning value exists; the features whose "
        "settings were born tuned are switched off. Never measured. Fit, do not deploy."
    ),
    overrides={
        # ── Features OFF — Aaron's call, 2026-09-17 ───────────────────────────────
        # Each of these was OFF at the original port, so off is the restored value and
        # not a new choice. Switching them off also makes 20 born-tuned settings inert,
        # which is what stops this baseline from containing invented numbers.
        "exec_scale_in": False,      # was False until 2026-09-06 (a4b71b8e)
        "exec_secondary": False,     # was False at introduction (859672d6)
                                     #   — takes the reclaim half with it
        "exec_time_stop_mode": "Off",   # born tuned (f46150ac); the feature did not
                                        #   exist at the port, so Off is its absent state

        # ── Restored originals — each moved by a measurement taken ON GOLD ────────
        "exec_tp1_pct": 30.0,        # was 30.0 → 0.0 by Run 1 (45b17ff6)
        "exec_tp2_pct": 40.0,        # was 40.0 → 0.0, same commit
        "exec_runner_trail": "Structure (swing)",   # was the swing trail (88042167);
                                     #   the ratchet is a gold measurement (a392e791)
        "exec_min_atr_pct": 0.0,     # was 0.0 → 0.08 off a gold drawdown column (ce35c0b5)
        "exec_sec_tp1_pct": -1.0,    # was the -1 sentinel (e1498a1d); inert here anyway
    },
)

# ── What is deliberately NOT reverted, and why ────────────────────────────────────
#
# `exec_risk_pct` (5.0) — NOT reverted to its original 10.0. It was moved on 2026-09-13
#   to match this bot's share of the 10% account risk cap, which is an ACCOUNT decision,
#   not a gold measurement. Reverting it would double per-trade risk on a pair nobody has
#   measured. It stays where the account rule puts it.
#
# `exec_sl_level` ("0.886") — NOT reverted to its original "1.0". The move was a sync to
#   Aaron's own TradingView chart configuration (a392e791), not a sweep, so there is no
#   gold fit to undo. ⚠ OPEN: it is still a stop-placement choice made while looking at
#   gold, and it decides the setup's R. Worth sweeping per instrument; flagged rather
#   than silently changed.
#
# `exec_min_stop_mode` / `exec_min_stop_val` ("% of price", 0.08) — NOT switched off,
#   although 0.08 IS a gold measurement. This is a SAFETY guard, not an optimisation:
#   position size is risk divided by stop distance, so a collapsing stop balloons the
#   quantity. Turning the floor off to be "untuned" would remove the guard that exists
#   for that hazard. ⚠ The VALUE is gold's and must be re-measured per instrument; the
#   MODE stays on while that happens.
#
# `exec_scale_tp_mode` ("Ride") and `exec_sec_once_per_setup` (True) — their originals
#   were a shipped defect and a pre-bugfix behaviour respectively, not untuned values.
#   Restoring a bug is not reverting a fit. Both are inert here regardless.


PROFILES = {p.name: p for p in (GOLD, UNTUNED)}
