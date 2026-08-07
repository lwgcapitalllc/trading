"""BosConfig — the MPC BOS bot's config.

A strict SUPERSET of `mpc_sos_fade`'s `SosFadeConfig`, exactly like `BLegConfig`: the BOS
strategy runs the SAME engine stack and the SAME exit ladder, and its ENTRY ladder is the
A+'s (spec §5), only priced off the BOS leg instead of the SOS leg. So every A+ exit input
still matters and is inherited; the new fields are the BOS setup's own (spec §8).

⚠ **EVERY FIELD HERE HAS A `mpc_bos_strategy.pine` INPUT BEHIND IT AND NOTHING ELSE DOES.**
The deleted 2026-08-04 port carried eight research dials with no Pine counterpart
(`bos_entry_source`, `bos_exit_mode`, `bos_rr_tp1/2`, `bos_max_atr_pct`, `bos_min_atr_pct`,
`bos_max_atr_rel`, `bos_no_ny_pm`, plus a `"Break leg origin"` stop model), and a config
field the export cannot carry is a field `compare_bos.py` can never check — so a run using
one is unverifiable by construction, which is a large part of why that port was deleted.
Recover them from `1946f8b^` if the Pine ever grows the inputs; do not re-add them here first.

Defaults MATCH the Pine field for field, as of the 2026-08-07 default change (Run 7 in
`docs/MPC_BOS_OPTIMIZATION.md`). Where this fork ships a different default from the A+ Pine,
the value is re-declared below WITH THE REASON — an inherited default is a default nobody
chose, and this repo has been bitten by that in both directions.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from mpc_sos_fade.config import SosFadeConfig  # noqa: E402


@dataclass(frozen=True)
class BosConfig(SosFadeConfig):
    """`mpc_bos_strategy.pine`'s Strategy Execution panel, field for field."""

    # ── 1. WHAT TRADES (Pine execLongs / execShorts) ─────────────────────────────
    # Inherited: exec_longs / exec_shorts, both True.

    # ── Inherited A+ toggles, re-defaulted to THIS fork's Pine values ─────────────
    exec_aplus: bool = False
    #   There is no A+ path in this fork at all — the arm is a BOS, not a swept SOS. Pinned
    #   False so the parent's `_armed` can never place an order behind this fork's back.
    exec_bleg: bool = False        # nor a B-LEG one
    exec_secondary: bool = False
    #   🔴 PINNED, and it is the one that would break the LAB rather than the strategy. The
    #   parent defaulted the 1-minute re-entry ON on 2026-08-07, and it needs a second bar
    #   stream through `run_dual`. This fork has no `run_dual` (there is no BOS 1m leg in any
    #   Pine), and `backtest.optimizer.run_sweep` takes ONE frame — so an inherited True would
    #   refuse every BOS sweep and optimizer grid the day this package landed. Same shape as
    #   `mpc_bleg`'s pin, same reason.
    exec_conf_sz: bool = True
    #   Pine execConfSZ (line 473) — the engine-side Sniper Zone TRACKER, which this fork ships
    #   ON where the A+ ships OFF. It only decides whether the zone is COMPUTED; whether the
    #   zone may price an entry is `bos_use_fvg` + `exec_conf_sz2` below.
    exec_deep_fib: bool = True
    #   Pine execDeepFib (Method 3) — PINNED. The parent defaulted it True → False on
    #   2026-08-02 when its four-rule entry model replaced Method 3; this fork's Pine still
    #   ships `true` and has none of those rules, and `BosExecution._entry_edges` reads this
    #   flag itself. Inheriting the parent's new default would silently switch Method 3 off.
    exec_fib_overlap: bool = False    # the parent's rule 1 — absent from this fork's Pine
    exec_fib_deep_edge: bool = False  # the parent's rule 2 — absent from this fork's Pine
    exec_fib_nearest: bool = False
    #   🔴 PINNED False, and this is the one that MOVES TRADES if inherited. The parent defaults
    #   it ON, and it is a different entry price: it rests on whichever bracketing fib is nearer
    #   the gap edge, where Method 3 always takes the shallower one. `mpc_bos_strategy.pine` has
    #   no `execFibNearest` input, so an inherited True would price every gap entry at a level
    #   the Pine never chose — invisible to the gate, because the export has no column for it.
    exec_fvg_pre_zone: bool = False   # the parent's pre-zone gate — absent from this fork's Pine
    exec_fvg_50: bool = False         # Pine execFvg50 — a gap STRADDLING the shallow end
    exec_runner_trail: str = "Structure (swing)"
    #   PINNED — this fork's Pine ships the TWO-option dropdown ("Fixed step" / "Structure
    #   (swing)"). The parent moved to "Structure + % ratchet" on 2026-07-28. Un-pin only in the
    #   same commit that ports `f_swingRatchet` + `execTrailPct` into `mpc_bos_strategy.pine`.
    exec_time_stop_mode: str = "Off"
    #   PINNED — the parent defaulted the 36h time stop ON on 2026-08-06 and this fork's Pine has
    #   no `execTimeStopMode` input. The plateau behind that default was measured on A+ trades;
    #   a continuation trade is a different hold, so inheriting it would apply an unmeasured cut.
    exec_sl_level: str = "1.0"
    #   Unused here — the stop comes from `bos_sl_model`. Declared so the parent's `_sl_anchor`
    #   cannot be reached with a value this fork never chose.
    exec_respect_veto: bool = False   # unused here — the BOS veto is `bos_respect_veto`
    exec_close_opp_sos: bool = False  # unused here — the BOS close is `bos_close_opp_div`
    exec_no_late_day: bool = True     # Pine execNoLateDay (F7) — a market-hours fact
    exec_htf_weekly: str = "Ignore"   # Pine execHtfWeekly
    exec_htf_daily: str = "Ignore"    # Pine execHtfDaily
    exec_htf_exhaust_only: bool = False  # not an input in this fork's Pine

    # ── 2. WHAT ARMS IT — the break (spec §4, Pine section 2) ────────────────────
    bos_which: str = "All"             # F1 ∈ {"1st only", "1st + 2nd", "All"}
    #   Which break after the shift may arm. Defaulted "1st only" → "All" 2026-08-07: taking
    #   every break measured better at the 0.786 entry depth.
    bos_min_disp_atr: float = 0.0      # F2 — the break must CLOSE past the swing by N × ATR(14)
    bos_min_leg_atr: float = 0.0       # F3 — break-leg range floor, 0 = off
    bos_max_days: float = 3.0          # F9 — armed-BOS staleness, DAYS → a bar count
    bos_max_per_regime: int = 10       # F6 — filled trades since the last SOS; 10 ≈ off
    bos_req_hold: bool = False
    #   F4 — a close back through the broken swing kills the setup. OFF BY MEASUREMENT, not by
    #   omission: the entry band sits BELOW the broken swing on almost every leg, so price cannot
    #   reach the limit without first closing back through the level, and F4 killed the setup a
    #   few bars before its own order would have filled (13 trades in a year). Spec §10b.

    # ── 3. WHERE THE LIMIT RESTS (Pine section 3) ────────────────────────────────
    bos_fib_anchor: str = "Break leg"  # ∈ {"Expansion leg", "Break leg"}
    #   Which leg the entry band, the stop and the targets are measured on. Defaulted
    #   "Expansion leg" → "Break leg" 2026-08-07, and the reason is HONESTY rather than a
    #   measured win: every number behind today's defaults came from a skeleton that froze the
    #   leg at the break bar. "Expansion leg" has NOT been measured head-to-head.
    bos_entry_top: str = "0.5"         # ∈ {"0.5", "0.382"} — the SHALLOW end of the entry band
    #   The deep end (0.886) is fixed and does not move with this.
    bos_use_fvg: bool = False
    #   🔴 Defaulted True → False 2026-08-07 and it was the losing half of the book. Two
    #   independent measurements: the 2026-07-31 sweep found the FVG entry was 98 trades for
    #   −15.1R with no winner bigger than +3.3R, and the 2026-08-06 engine study found a plain
    #   0.786 fib beats it +14.5% vs +3.7% over a matched random control. The gap decides where
    #   the limit rests, and it rests too shallow for a continuation trade.
    exec_req_fvg: bool = True          # Pine execReqFVG — no gap = no trade (inert while off)
    exec_fvg_deep_only: bool = True    # Pine execFvgDeepOnly — the gap must sit fully past lTop
    exec_conf_sz2: bool = True         # Pine execConfSZ2 — the Sniper Zone COUNTS as a gap
    bos_entry_fib: str = "0.786"       # ∈ {"0.382","0.5","0.618","0.702","0.786","0.886"}
    #   ⚠ SINCE 2026-08-07 THIS IS THE PRIMARY ENTRY, NOT A FALLBACK — `bos_use_fvg` is off, so
    #   this level is what actually trades. The name is the Pine's and is kept deliberately.
    #   ⚠ Do NOT pair it with a tighter stop: 0.786 against a 0.886 stop scored higher on paper
    #   and is a trap (median stop $0.74, so the $0.22 spread is 30% of R).

    # ── 4. WHAT CAN REFUSE IT (spec §4) ──────────────────────────────────────────
    bos_respect_veto: bool = False     # F5 — divergence / extreme RSI blocks a NEW entry (LIVE)
    bos_vwap_req: str = "Trend's side"  # F10 ∈ {"Off", "Trend's side"}
    #   The session VWAP filter, added 2026-08-06 and the only MEASURED default here: it roughly
    #   doubles this trigger's edge over a matched random control (+4.4% → +6.8%) and cuts the
    #   median stop distance 38%. ⚠ Set "Off" to reproduce anything measured before it existed.
    #   ⚠ It is the ONLY field in this file that needs the bar's VOLUME — see `bos.py`.

    # ── 5. SIZE & STOP (spec §6) ─────────────────────────────────────────────────
    bos_sl_model: str = "ATR"
    #   ∈ {"Fib 1.0 (leg origin)", "Broken swing level", "Fib 0.886", "Last confirmed swing", "ATR"}
    #   Defaulted "Fib 1.0" → "ATR" 2026-08-07, the largest single improvement measured on this
    #   strategy. A fib stop is a FRACTION OF THE LEG, so a small leg produces a small stop
    #   mechanically (median $1.58, tightest tenth $0.64, where the $0.22 spread is 34% of R and
    #   a 15-minute bar cannot resolve the touch); an ATR stop does not care how big the leg was
    #   (median $3.89, tightest tenth $2.06).
    #   ⚠ "Broken swing level" is largely INOPERABLE and is not a real option: for a long that
    #   level sits ABOVE the entry, so `dist = entry − stop` is negative and the order is refused.
    #   It is kept only because the Pine has it.
    bos_sl_atr: float = 1.3            # ATR model only. 1.2–1.5 is one plateau inside the noise.
    exec_min_stop_mode: str = "% of price"   # inherited value, and this fork's Pine agrees
    bos_move_stop: str = "Off"         # Pine execMoveStop ∈ {"Off","$ of price","Structure (swing)"}
    bos_move_stop_val: float = 5.0     # Pine execMoveStopVal — DOLLARS in "$ of price", TICKS in "Structure"
    #   🔴 NEW FIELDS — `SosFadeConfig` has no moving stop at all, so there was nothing to
    #   inherit. It is a trail that runs from the bar AFTER the fill instead of waiting for TP2
    #   like the runner trail: it follows the best price the trade has seen and can only ever
    #   pull the stop TIGHTER, never loosening breakeven or the TP2 floor, and the two compose.
    #   ⚠ They exist because the EXPORT carries them (`cfg_enum1`, `cfg_move_stop_val`), and a
    #   Pine input the Python cannot express is a setting `compare_bos.py` would decode into
    #   nothing — a run taken with it ON would diverge with no field to name.
    exec_min_stop_val: float = 0.10
    #   ⚠ NOT the A+ value (0.08). This fork's Pine ships 0.10, and at the ATR stop model it only
    #   refuses ~7 setups in 168. ⚠ It is NOT free to move the stop model back to a fib without
    #   it: at "Fib 1.0" this floor cuts the book from 168 trades to 55.

    # ── 6. TARGETS (Pine section 6) ──────────────────────────────────────────────
    # exec_tp1_pct / exec_tp2_pct are inherited at 0.0, which is this fork's Pine default too.
    exec_tp3_pct: float = 100.0
    #   🔴 NEW FIELD — the A+ ladder has TP1/TP2 and a runner, and this fork's Pine adds a THIRD
    #   rung at fib 0.000 (the leg extreme). Defaulted 20 → 100 on 2026-08-07, so there is NO
    #   RUNNER: the whole position exits at TP3 or at the ratcheting stop. That measured best on
    #   every axis — +137.7R vs +90.8R for 30/30/20 and +113.4R for a pure runner, at the same
    #   drawdown, a higher t-stat and less concentration. Whatever you leave under 100 becomes
    #   the runner again.
    bos_tp3_measured: bool = False     # TP3 = the break leg's range projected from the broken level
    bos_close_opp_div: bool = False    # close an OPEN trade on a confirmed opposing divergence

    # `exec_be_buf_tk` (30), `exec_trail_step` (5.0), `exec_struct_trail_buf_tk` (20),
    # `exec_tp2_stop_mode` ("TP1 price") and `exec_sl_buf_tk` (0.0) are inherited unchanged —
    # this fork's Pine ships the identical values, checked field by field 2026-08-07.

    def __post_init__(self) -> None:
        """Refuse a value the Pine's dropdowns cannot produce, rather than falling back.

        A string typo in a lab param would otherwise pick the `else` branch of a ternary —
        `bos_sl_model = "atr"` would silently take the fib-1.0 stop and replay a whole
        backtest against a level nobody chose, reported as theirs. Same reasoning as
        `exec_sl_custom`'s range check in the parent.

        ⚠ The `super()` call is load-bearing, not politeness: the parent validates
        `exec_time_stop_mode` and `exec_sl_custom` here, and a subclass that defines
        `__post_init__` REPLACES it — so omitting the call would quietly retire two
        checks this fork still inherits the fields for. Pinned by a test.
        """
        super().__post_init__()
        _one_of("bos_which", self.bos_which, ("1st only", "1st + 2nd", "All"))
        _one_of("bos_fib_anchor", self.bos_fib_anchor, ("Expansion leg", "Break leg"))
        _one_of("bos_entry_top", self.bos_entry_top, ("0.5", "0.382"))
        _one_of("bos_entry_fib", self.bos_entry_fib,
                ("0.382", "0.5", "0.618", "0.702", "0.786", "0.886"))
        _one_of("bos_vwap_req", self.bos_vwap_req, ("Off", "Trend's side"))
        _one_of("bos_move_stop", self.bos_move_stop,
                ("Off", "$ of price", "Structure (swing)"))
        _one_of("bos_sl_model", self.bos_sl_model,
                ("Fib 1.0 (leg origin)", "Broken swing level", "Fib 0.886",
                 "Last confirmed swing", "ATR"))
        if self.bos_max_days <= 0:
            raise ValueError("bos_max_days must be > 0 (Pine minval 0.25)")
        if self.bos_max_per_regime < 1:
            raise ValueError("bos_max_per_regime must be >= 1 (Pine minval 1)")
        if self.bos_sl_atr <= 0:
            raise ValueError("bos_sl_atr must be > 0 (Pine minval 0.1)")


def _one_of(name: str, value: str, allowed: tuple) -> None:
    if value not in allowed:
        raise ValueError(
            f"{name}={value!r} is not one of {allowed}. "
            "These mirror the Pine input's own options; a value outside them cannot be "
            "exported, so a run using one could never be checked by compare_bos.py."
        )
