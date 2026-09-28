"""SosFadeGenericConfig — the few settings SOS Fade Generic exposes, and how they map.

🔴 **THIS IS NOT A SECOND SOS FADE.** Every decision — the sweep, the divergence, the structure
shift, the fib, the gap, the limit price, the fill, the sizing — is made by the SOS Fade code in
`strategies/python/sos_fade/`, which is parity-gated against `sos_fade_strategy.pine`. This file
only decides WHICH of SOS Fade's settings the lab shows, and pins every other one OFF.

Spec: `docs/SOS_FADE_GENERIC_SPEC.md`.

⚠ **Field names are SOS Fade's own where the meaning is identical**, so the lab row, the Pine
input and this field are one setting with one name (`docs/STRATEGY_WORKFLOW.md`). The one new
field is `gen_target`, because "where the whole trade closes" is a choice SOS Fade spells as
three settings together.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from sos_fade.config import SosFadeConfig  # noqa: E402

#: The target choices, and what each one sets on SOS Fade: (first-rung fib level, first rung in R).
#: The whole position closes at that one rung — see `to_sos_fade`.
TARGETS = {
    "Swing high/low": ("0.0", -1.0),
    "1R": ("Auto", 1.0),
    "2R": ("Auto", 2.0),
    "3R": ("Auto", 3.0),
}


@dataclass(frozen=True)
class SosFadeGenericConfig:
    # ── what trades ──────────────────────────────────────────────────────────────
    exec_longs: bool = True            # "Trade longs"
    exec_shorts: bool = True           # "Trade shorts"
    exec_risk_pct: float = 5.0         # "Risk % per trade"
    # ── what arms it ─────────────────────────────────────────────────────────────
    #   BOTH on by default, which is the one place this differs from SOS Fade's own default
    #   (sweep only). Aaron's rule for this bot: "armed on divergence or a sweep".
    exec_arm_sweep: bool = True        # "Arm on liquidity sweep"
    exec_arm_div: bool = True          # "Arm on RSI divergence"
    aplus_window: int = 4320           # "Max time: sweep → SOS (minutes)"
    # ── entry ────────────────────────────────────────────────────────────────────
    #   On = the pullback must reach a gap in the zone and the limit rests on the fib nearest it.
    #   Off = a gap is still used when there is one; with none the limit rests at the 0.618.
    exec_req_fvg: bool = True          # "Require an FVG in the zone"
    # ── exit ─────────────────────────────────────────────────────────────────────
    #   The stop is ALWAYS the 1.0 fib (the start of the move) and is not a setting.
    gen_target: str = "Swing high/low"  # "Take profit at" ∈ TARGETS
    # ── the one guard kept ───────────────────────────────────────────────────────
    #   A SIZING safety, not an entry filter: size = risk / stop distance, so a stop sitting on
    #   the entry would buy an enormous position. Kept at SOS Fade's shipped floor.
    exec_min_stop_mode: str = "% of price"  # "Minimum stop distance"
    exec_min_stop_val: float = 0.08    # "Minimum stop floor (unit = mode above)"
    # ── instrument & fills (foundational — the lab keeps these off the tuning surface) ────
    #   ⚠ `mintick` is overridden by the run's cost profile when it has one — see the strategy.
    mintick: float = 0.01
    point_value: float = 1.0
    fill_model: str = "bar"
    account_profile: str = "vantage_demo"
    symbol: str = "XAUUSD"

    def __post_init__(self) -> None:
        if self.gen_target not in TARGETS:
            raise ValueError(
                f"gen_target must be one of {list(TARGETS)}, got {self.gen_target!r}")
        if not (self.exec_arm_sweep or self.exec_arm_div):
            # Refused rather than run: with both arms off nothing can ever trade, and a run of
            # zero trades reads as "no edge here" on an instrument that was never tested.
            raise ValueError("both arms are off, so nothing can ever trade — switch on "
                             "'Arm on liquidity sweep' or 'Arm on RSI divergence'")

    def to_sos_fade(self) -> SosFadeConfig:
        """The SOS Fade config this bot runs: these settings, the 1.0 stop, one target, nothing else.

        🔴 **Every SOS Fade feature with a default that is ON is named here and switched OFF.**
        Leaving one to its default is how a "simple" bot would quietly re-acquire the thing it
        exists to strip out — `tests/test_config.py` holds this list against the fields.
        """
        tp_level, tp_r = TARGETS[self.gen_target]
        return SosFadeConfig(
            # the settings this bot exposes
            exec_longs=self.exec_longs,
            exec_shorts=self.exec_shorts,
            exec_risk_pct=self.exec_risk_pct,
            exec_arm_sweep=self.exec_arm_sweep,
            exec_arm_div=self.exec_arm_div,
            aplus_window=self.aplus_window,
            exec_req_fvg=self.exec_req_fvg,
            exec_min_stop_mode=self.exec_min_stop_mode,
            exec_min_stop_val=self.exec_min_stop_val,
            mintick=self.mintick,
            point_value=self.point_value,
            fill_model=self.fill_model,
            account_profile=self.account_profile,
            symbol=self.symbol,
            # the stop: the 1.0 fib, no buffer
            exec_sl_level="1.0",
            exec_sl_deep=False,
            exec_sl_buf_tk=0.0,
            # the target: ONE rung that closes the whole position
            exec_tp1_level=tp_level,
            exec_tp1_r=tp_r,
            exec_tp1_pct=100.0,
            exec_tp2_pct=0.0,
            # entry: SOS Fade's own zone rules; "no gap" means any no-gap setup may rest at 0.618
            exec_nogap_arm="Any",
            exec_poi_source="FVG",
            exec_conf_sz=False,
            # filters — all off
            exec_respect_veto=False,
            exec_htf_exhaust_only=False,
            exec_htf_weekly="Ignore",
            exec_htf_daily="Ignore",
            exec_no_late_day=False,
            exec_min_atr_pct=0.0,
            exec_entry_block_from="",
            exec_entry_block_to="",
            # trade management — all off
            exec_close_opp_sos=False,
            exec_time_stop_mode="Off",
            exec_be_arm_r=-1.0,
            exec_giveback_arm_r=-1.0,
            exec_rev_exit="Off",
            exec_scale_in=False,
            flat_mode="Off",
            # extra trade types — all off
            exec_bleg=False,
            exec_secondary=False,
            exec_recovery=False,
            exec_short_hold=False,
            exec_lvl_memory=False,
        )
