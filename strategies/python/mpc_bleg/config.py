"""BLegConfig — the B-LEG bot's config.

It is a strict SUPERSET of `mpc_sos_fade`'s `SosFadeConfig`: the B-LEG runs the SAME
engine stack + A+ SEQUENCE tracker (it arms off the A+ death), and it keeps the "A+ has
priority" gate — so every A+ input still matters (the priority gate reads the A+ arm
sources, edges, veto, HTF filters). Inheriting keeps the two in lockstep: a new A+ toggle
lands here for free. The only NEW field is `bleg_max_days` — how long a frozen B-LEG band
watches for the late retrace before it goes stale (Pine input "Days to watch for the late retrace").

The exit ladder / sizing / cost fields (`exec_risk_pct`, `exec_tp1_pct`, `exec_be_buf_tk`,
`exec_trail_step`, `fill_model`, `account_profile`, …) are reused verbatim — the B-LEG
trades through the SAME execution machinery, only the ENTRY (band edge, custom SL/TP) and
the arm differ. See `bleg.py` / `execution.py`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# strategies/python on path so `mpc_sos_fade` imports by bare name (same shim the tests use).
_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from mpc_sos_fade.config import SosFadeConfig  # noqa: E402


@dataclass(frozen=True)
class BLegConfig(SosFadeConfig):
    # ── Inherited toggle, re-defaulted to this fork's Pine value ───────────────────
    exec_bleg: bool = True  # "Trade B-Leg setups" — THIS fork's core setup, so ON here
    #   `mpc_b_leg_strategy.pine` ships execBLeg = true (the A+ file ships it false). Turn OFF
    #   only to prove the bot trades nothing without it. `exec_aplus` is inherited and still
    #   matters: A+ never PLACES an order here, but it holds the priority gate — set it False
    #   to drop that gate and read the B leg completely on its own.
    exec_sl_level: str = "1.0"  # "Stop fib level" — pinned, NOT inherited
    #   The parent defaulted this "1.0" → "0.886" on 2026-07-27 to match the A+ Pine. This fork's
    #   Pine (`mpc_b_leg_strategy.pine`) still ships "1.0", and toggle-default parity with its OWN
    #   Pine is the contract, so the value is pinned here rather than inherited. It is also unused
    #   on this path — a B leg's stop is the frozen band's origin, never the fib anchor — so the
    #   pin costs nothing and only stops a silent drift between this config and its export.
    #   ── the 2026-08-02 A+ entry model — PINNED to the pre-2026-08-02 behaviour ──────────────
    #   `mpc_b_leg_strategy.pine` has none of these inputs and still ships `execDeepFib = true`,
    #   so this fork must keep Method 3 and nothing else, or it drifts from its OWN Pine.
    #   NOT inert, which is why they are pinned rather than left to the parent's defaults: this
    #   fork overrides `_place_entries` but NOT `_entry_edges`, and the edges it produces feed
    #   `_armed()` — the "A+ has priority, stand the B leg down" gate. A different A+ entry edge
    #   therefore changes which bars the B leg is allowed to trade on.
    exec_deep_fib: bool = True  # the parent defaulted this True → False on 2026-08-02
    exec_fib_nearest: bool = False  # rule 3 — the parent's new default, absent from this Pine
    exec_fib_overlap: bool = False  # rule 1 — absent from this Pine
    exec_fib_deep_edge: bool = False  # rule 2 — absent from this Pine
    exec_fvg_pre_zone: bool = False  # the pre-zone gate — absent from this Pine
    exec_sl_deep: bool = False  # the deep-entry stop override — absent, and unused here
    exec_secondary: bool = False  # the 1m sniper re-entry — pinned OFF, and NOT inert
    #   The parent defaulted this True on 2026-08-07. It is an A+ feature end to end: it re-enters
    #   a 15m A+ leg whose PRIMARY reached breakeven, and in this fork A+ never places an order, so
    #   there is no primary for it to follow. `MpcBLegStrategy.run_dual` raises outright.
    #   ⚠ **Pinned rather than left to inherit, because inheriting it BREAKS this bot rather than
    #   quietly changing it**: the lab reads `exec_secondary` off the config to decide whether to
    #   load a 1m feed and call `run_dual`, so an inherited True makes every B-LEG lab run die on
    #   that NotImplementedError. Same class as the `exec_min_stop_mode` pin below — a parent
    #   default that this fork's code cannot honour — but the failure is loud instead of silent,
    #   which is the only reason it was caught rather than shipped.
    exec_nogap_arm: str = "Any"  # "↳ No-FVG entries need" — pinned, and INERT here
    #   Added to the parent 2026-08-10 to gate its no-FVG fallback entry. Pinned to the inert
    #   value for the same reason as `exec_min_stop_mode` below: it is read only when
    #   `exec_req_fvg` is False, which this fork inherits as True, so it cannot fire today — and
    #   pinning stops a future parent default silently claiming a filter this fork does not run.
    #   ⚠ It is PYTHON-ONLY on the parent (no `execNoGapArm` input in either A+ Pine), so
    #   `mpc_b_leg_strategy.pine` has nothing to be parity-checked against and inheriting a
    #   non-default would put `compare_bleg.py` red with no export column able to explain it.
    #   ⚠ Not inert by ACCIDENT: this fork overrides `_place_entries` but NOT `_entry_edges`, and
    #   those edges feed the "A+ has priority" gate — so if `exec_req_fvg` is ever turned off
    #   here, this field starts deciding which bars the B leg may trade on. Sweep it then.
    exec_min_stop_mode: str = "Off"  # "Minimum stop distance" — pinned OFF, and INERT here
    #   Inherited from the parent, which added it 2026-07-30 as the guard for a stop that collapses
    #   onto the entry. It does NOT apply on this path: the floor is enforced in the parent's
    #   `_place_entries`, which `BLegExecution` overrides, and `mpc_b_leg_strategy.pine` has no such
    #   input to be parity-checked against. Pinned to the inert value so a future parent default
    #   change cannot silently claim a guard this fork does not run. The hazard it protects against
    #   is also structurally absent here — a B leg's stop is the band ORIGIN, always a full band
    #   away from the 0.5 entry edge, never a fib that can land on top of it.
    #   Porting it means adding the input to that Pine, the floor check to `_place_entries`, and a
    #   `cfg_min_stop` column to the B-LEG export — in one commit, then re-run `compare_bleg.py`.

    #   `exec_runner_trail` was PINNED to "Structure (swing)" here from 2026-07-28 until later the
    #   same day, because the parent had moved to "Structure + % ratchet" while this fork's Pine
    #   still shipped the two-option dropdown — inheriting would have moved every B-LEG runner exit
    #   against a Pine that stood still, and `compare_bleg.py` would have reported the drift as a
    #   bug. `mpc_b_leg_strategy.pine` now carries the ratchet (same `f_swingRatchet`, same default),
    #   so the pin is GONE and `exec_runner_trail` / `exec_trail_pct` are inherited again. The
    #   43% → 53% run-capture number behind that default was measured on the parent's A+ trades,
    #   never on B legs — it is inherited for ONE-LADDER consistency, not as a proven B-LEG result.
    #   Sweep it here before treating it as tuned.

    exec_trail_pct: float = 0.05  # "Runner ratchet step (% of price)" — RE-DEFAULTED for this fork
    #   The parent ships 1.0 and that value is right THERE and structurally wrong here, for a
    #   reason that is about units rather than about tuning. The step is a percent of PRICE,
    #   while a B leg's whole 1R is 0.13%-1.25% of price (measured, 2026-08-06, over the 50
    #   baseline trades: stop distances $2.51 to $49.02). At 1.0 one trail step is routinely
    #   LARGER THAN THE ENTIRE RISK, so `f_swingRatchet` can never climb above the stage-2 floor
    #   and the ratchet is inert — the runner is capped at that floor on every trade.
    #   ⚠ And the floor is exactly 1R here, by construction rather than by choice: TP1 is
    #   `2*edge - inv` and the stop is `inv`, so TP1 - edge == edge - inv. With
    #   `exec_tp2_stop_mode` at its inherited "TP1 price" the runner therefore banks precisely
    #   +1.00R and hands back everything above it. Nine of the 50 baseline trades exited at
    #   exactly +1.00R, one of them after running +6.82R; across all 50 the sum of maximum
    #   favourable excursion was 73.9R against a captured -0.9R.
    #   MEASURED by real replay, 186,312 M15 bars (2018-09-13 -> 2026-08-05), spread + swap
    #   charged, alongside bleg_max_days below — see this package's CLAUDE.md for the grid.
    #   ⚠ 0.05 is the Pine input's own `minval`, and the plateau genuinely continues below it —
    #   but that lower half is a BAR-GRANULARITY artefact, not a market fact: a $2 step and a
    #   $0.25 step exit on the same 15m bar, which is why 0.03 / 0.02 / 0.01 all returned the
    #   identical figure to the cent. Do not read that flatness as headroom.
    #   ⚠ INHERITED BY NOTHING — `mpc_sos_fade` keeps 1.0. Its own measurement says the opposite
    #   (0.25% -> 43.6R against 109.3R at 1.0), because an A+ stop is a fib fraction of a leg on
    #   a ladder whose rungs are also fib levels. Do not "reconcile" the two.

    exec_time_stop_hrs: float = 8.0  # "Time stop (hours)" — RE-DEFAULTED for this fork
    #   The parent ships 36.0 and BOTH numbers are measured, on their own trades, and they
    #   disagree — so this is pinned rather than inherited, the same call as exec_trail_pct
    #   above. `exec_time_stop_mode` is NOT pinned: "Before TP1 only" is right on both forks.
    #   MEASURED 2026-08-06 by real replay, 186,312 M15 bars (2018-09-13 -> 2026-08-05),
    #   spread + swap charged, one axis moved off the shipped baseline per row:
    #       Off  111 / +6.50R  / PF 1.11 / maxDD -12.01
    #       36h  112 / +12.02R / PF 1.23 / maxDD  -8.89   (the inherited value)
    #       18h  113 / +15.54R / PF 1.33 / maxDD  -8.10
    #       12h  113 / +15.21R / PF 1.35 / maxDD  -6.03
    #        8h  114 / +17.56R / PF 1.45 / maxDD  -5.15   <- shipped
    #        6h  114 / +14.37R / PF 1.38 / maxDD  -5.13
    #        4h  114 / +13.32R / PF 1.39 / maxDD  -5.19
    #   ⚠ 8 is defensible because 4-12 is a PLATEAU on drawdown (all near 5R against 8.89R
    #   at 36), not because it is the single highest R. Read the drawdown: +5.5R over 114
    #   trades in 7.9 years is inside a noise band this strategy has never had measured —
    #   the A+ jitter audit put THAT bot's run-to-run spread at sd 15.06R and no equivalent
    #   has been run here.
    #   ⚠ It cuts NO winners. The lever only fires at stage 0 (TP1 never touched), so the
    #   gain is dead trades ending sooner and the single position slot freeing up — not a
    #   runner being handled better.
    #   ⚠ THE OPPOSITE LEVER WAS MEASURED AND REJECTED, which is the part worth keeping.
    #   The exit-stage map over the 112 baseline trades reads: stage 0, 63 trades, -48.12R
    #   banked on 24.61R shown; stage 1 (touched +1R, stop at breakeven, never reached TP2),
    #   18 trades, -1.38R banked on 31.23R shown; stage 2 (runner trail live), 31 trades,
    #   +61.52R banked on 73.31R shown — 84% kept. Stage 1 looks like a 32R hole and every
    #   way of closing it LOST money: trailing from stage 1 gives +1.92R, flooring at +1R
    #   gives +4.09R, pulling TP2 to 60% gives +1.10R, pushing it to 180% gives -4.82R, and
    #   all four cut the best trade from +5.07R to under +4.4R. The breakeven-until-TP2 gap
    #   is what lets the stage-2 cohort run; protecting earlier saves the 18 and kills the 31.

    # ── B-LEG-only input (Pine bLegMaxDays, group "Strategy Execution") ─────────────
    bleg_max_days: float = 4.0  # days a frozen band watches before it goes stale (1-6)
    #   Converted to a BAR count (day ÷ chart timeframe) so weekends and the daily close
    #   don't burn the clock. 1.25 = the original 120 bars on 15m. See bleg.py.
    #   RE-DEFAULTED 1.25 -> 4.0 on 2026-08-06, and the interesting part is that the old value
    #   was not a tuned number at all — it was the Pine input's `maxval = 3` that mattered, and
    #   the best region sits OUTSIDE it. Charged, over the full broker history: 1.25 -> 59
    #   trades / +7.29R, 3.0 -> 92 / +10.56R, 4.0 -> 112 / +12.02R, 5.0 -> 118 / +13.76R,
    #   7.0 -> 121 / +8.62R. 4-5 days is a plateau and it degrades past it. 4.0 is chosen for
    #   the LOWEST drawdown in the plateau (-8.89R against 5.0's -10.41R) and the only clearly
    #   positive in-sample half, not for the highest total.
    #   ⚠ The Pine `maxval` was raised 3 -> 6 in the same commit. A cap is a claim about where
    #   the useful range ends, and this one had never been measured.
