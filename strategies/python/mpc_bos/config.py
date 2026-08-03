"""BosConfig — the MPC BOS bot's config.

A strict SUPERSET of `mpc_sos_fade`'s `SosFadeConfig`, exactly like `BLegConfig`: the BOS
strategy runs the SAME engine stack and the SAME exit ladder, and its ENTRY ladder is the
A+'s verbatim (spec §5, "use the A+ strategy's entry methods exactly as they are"), only
priced off the BOS leg instead of the SOS leg. So every A+ entry/exit input still matters
and is inherited; the new fields are the BOS setup's own (spec §8).

Defaults MATCH `indicators/mpc_bos_strategy.pine` field for field — toggle parity with its
own Pine is the contract, the same rule the other two bots follow. Where the BOS Pine ships
a different default from the A+ Pine, the value is re-declared here with the reason.
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
    # ── Inherited A+ toggles, re-defaulted to THIS fork's Pine values ─────────────
    exec_aplus: bool = False       # there is no A+ path in this fork at all
    exec_bleg: bool = False        # nor a B-LEG one
    exec_conf_sz: bool = True      # Pine execConfSZ — the engine-side Sniper Zone TRACKER
    #   Ships ON in `mpc_bos_strategy.pine` (line 433). It only makes the zone get COMPUTED;
    #   whether the zone prices an entry is `bos_use_fvg` + `exec_conf_sz2` below.
    exec_fvg_50: bool = False      # Pine execFvg50 — a gap STRADDLING 0.5 enters at 0.5
    #   Spec §5 wanted this ON here; the shipped Pine has it OFF, so the config matches the
    #   Pine. It is a live sweep candidate — see `exec_fvg_deep_only`, its mirror image.
    exec_deep_fib: bool = True     # Pine execDeepFib — PINNED, this fork's Pine still ships true
    #   The parent defaulted it True → False on 2026-08-02 when the new entry model (rules 1-3)
    #   replaced Method 3, but `mpc_bos_strategy.pine` line 3313 still ships `true` and has none
    #   of those rules. `BosExecution` fully overrides `_entry_edges` and reads this flag itself,
    #   so inheriting the parent's new default would silently switch Method 3 off here.
    exec_runner_trail: str = "Structure (swing)"   # PINNED — this fork's Pine has no ratchet
    #   The parent moved to "Structure + % ratchet" on 2026-07-28, but `mpc_bos_strategy.pine`
    #   still ships the TWO-option dropdown ("Fixed step" / "Structure (swing)"). Inheriting
    #   would move every BOS runner exit against a Pine that stood still. Un-pin only in the
    #   same commit that ports `f_swingRatchet` + `execTrailPct` into that Pine.
    exec_sl_level: str = "1.0"     # unused here — the stop model is `bos_sl_model`
    exec_no_late_day: bool = True  # Pine execNoLateDay (F7) — a market-hours fact
    exec_respect_veto: bool = False  # unused here — the BOS veto is `bos_respect_veto`

    # ── Setup (spec §8, Pine 3179-3201) ──────────────────────────────────────────
    bos_entry_fib: str = "0.618"   # ∈ {0.5, 0.618, 0.702, 0.786, 0.886}
    #   The FALLBACK entry — a plain limit at this retracement, no gap behind it. INERT at the
    #   shipped defaults: with `bos_use_fvg` and `exec_req_fvg` both on, the fib fallback is
    #   never reached.
    bos_fib_anchor: str = "Expansion leg"   # ∈ {"Expansion leg", "Break leg"}
    #   Which leg the entry fib / stop / targets are measured on. "Expansion leg" = the drawn
    #   External fib (bos_low → the running extreme), so the levels keep moving until the
    #   pullback confirms. "Break leg" = bos_low → bos_high, frozen at the BOS bar.
    bos_use_fvg: bool = True       # Pine bosUseFvg — price the entry off an FVG / Sniper Zone
    exec_conf_sz2: bool = True     # Pine execConfSZ2 — the Sniper Zone COUNTS as a gap
    #   ON, per Aaron's 2026-07-31 answer: the zone is optional confluence that can STAND IN
    #   for a missing FVG, never something the trade waits for.

    # ── NOT IN THE PINE — research dials added 2026-07-31 ────────────────────────
    # Run 1 split the book by the source that priced the entry and the two halves behave
    # completely differently: FVG-priced entries are −15.1R over 98 trades with no winner
    # bigger than +3.3R, Sniper-Zone-priced entries are +0.2R over 89 and hold every large
    # winner. These three dials exist to test the SZ half on its own terms. **They have no
    # `mpc_bos_strategy.pine` counterpart**, so any run using a non-default value is
    # research, NOT a candidate for the parity gate until the Pine gains matching inputs.
    bos_entry_source: str = "Any"  # ∈ {"Any", "Sniper Zone only", "FVG only"}
    #   Which ladder source may place an order. Isolates the two halves of the book.
    bos_exit_mode: str = "Fib ladder"   # ∈ {"Fib ladder", "Fixed R"}
    #   "Fib ladder" = the shipped behaviour (TP1/TP2 are fib levels chosen by entry depth,
    #   so the risk-reward ratio is an OUTPUT of leg geometry and cannot be dialled).
    #   "Fixed R" = TP1/TP2 sit at a MULTIPLE of the stop distance, which is what makes a
    #   "1:2" expressible at all. The stop still comes from `bos_sl_model`.
    bos_rr_tp1: float = 2.0        # TP1 in R, "Fixed R" mode only
    bos_rr_tp2: float = 4.0        # TP2 in R, "Fixed R" mode only
    #   A pure 1:2 = `bos_rr_tp1 = 2.0` with `exec_tp1_pct = 100` (bank the whole position
    #   at the target). Leave `exec_tp1_pct` at 0 and the target only STAGES the stop, which
    #   is a different strategy — see `mpc_sos_fade/CLAUDE.md` → The exit ladder.

    # ── Filters (spec §4) ────────────────────────────────────────────────────────
    bos_which: str = "All"             # F1 ∈ {"1st only", "1st + 2nd", "All"}
    bos_min_disp_atr: float = 0.5      # F2 — break must close past the swing by N × ATR(14)
    #   "Clean displacement" in Aaron's spec, expressed as a number. NOT a measured optimum.
    bos_min_leg_atr: float = 0.0       # F3 — break-leg range floor, 0 = off
    bos_req_hold: bool = False         # F4 — a close back through the broken swing kills it
    #   OFF by design, not by omission: the entry band sits BELOW the broken swing on almost
    #   every leg, so F4 kills the setup a few bars before its own limit would fill. See the
    #   Pine tooltip and spec §10b.
    bos_max_per_regime: int = 10       # F6 — filled trades since the last SOS; 10 ≈ off
    bos_max_days: float = 3.0          # F9 — armed-BOS staleness, in DAYS → a bar count
    bos_max_atr_pct: float = 0.0       # F10 — skip a setup when ATR14 exceeds this % of price
    bos_min_atr_pct: float = 0.0       # F10b — ...or falls below it. Both 0 = off.
    #   NOT IN THE PINE — added 2026-07-31 from the Run 3 feature study, which found the only
    #   characteristic that sorted outcomes consistently in BOTH halves of history: setups armed
    #   while ATR14 is a SMALL fraction of price behave differently from ones armed in fast
    #   conditions. It is a property of the market at the moment of the setup, not of the setup,
    #   which is why no existing input could express it.
    bos_max_atr_rel: float = 0.0       # F10c — skip a setup when ATR14 exceeds this MULTIPLE
    #   of the market's own ~10-day ATR baseline. 0 = off. The RELATIVE form of F10: an absolute
    #   %-of-price cap stops firing when the market's whole volatility level shifts (gold's median
    #   15m ATR went 0.081% of price in 2018 to 0.216% in 2026, so a 0.10% cap took ZERO trades in
    #   2026). This asks "quiet FOR THIS MARKET" instead, so it keeps working across regimes.
    bos_no_ny_pm: bool = False         # F11 — skip entries 12:00-16:00 New York
    #   Also from Run 3: that window is the only clock slice negative in both halves.
    bos_respect_veto: bool = False     # F5 — divergence / extreme RSI blocks entry (LIVE)
    bos_close_opp_div: bool = False    # F5b — close an OPEN trade on a confirmed opposing div

    # ── Risk / exits (spec §6) ───────────────────────────────────────────────────
    bos_sl_model: str = "Fib 1.0 (leg origin)"
    #   ∈ {"Fib 1.0 (leg origin)", "Broken swing level", "Fib 0.886", "Last confirmed swing",
    #      "ATR", "Break leg origin"}
    #   ⚠ "Broken swing level" is largely INOPERABLE and is not a real option: for a long the
    #   broken swing sits ABOVE the entry, so `dist = entry − stop` is negative and the order is
    #   refused. It placed 15 orders in 7.9 years (the rare leg that expanded far enough for the
    #   entry band to clear the broken level). Kept only because the Pine has it.
    #   "Break leg origin" is NOT in the Pine — added 2026-07-31. It is the structural
    #   continuation stop the spec's prose describes but its dropdown never offered: the low the
    #   break leg started from (long) / the high (short). Unlike "Broken swing level" it is
    #   always on the correct side of the entry.
    bos_sl_atr: float = 1.5            # ATR model only
    bos_tp2_measured: bool = False     # TP2 = the break-leg range projected from the broken level
