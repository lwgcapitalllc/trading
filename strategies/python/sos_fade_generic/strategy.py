"""SosFadeGenericStrategy — SOS Fade with everything but the core switched off.

It IS `SosFadeStrategy`, built from the SOS Fade config that `SosFadeGenericConfig.to_sos_fade`
produces. Nothing here decides a trade; see `config.py` for why that is the whole design.

⚠ **`self.config` is the SOS Fade config, not the generic one**, because every layer underneath
(and the stack runner, and the setup reports) reads SOS Fade's field names off it. The generic
settings the run was given are kept on `self.generic_config`.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from sos_fade.strategy import SosFadeStrategy  # noqa: E402

from .config import SosFadeGenericConfig  # noqa: E402


class SosFadeGenericStrategy(SosFadeStrategy):
    def __init__(self, config: Optional[SosFadeGenericConfig] = None,
                 initial_capital: float = 1_000_000.0, tick_source=None,
                 cost_profile=None, account=None, leg: str = "strat") -> None:
        self.generic_config = config or SosFadeGenericConfig()
        inner = self.generic_config.to_sos_fade()
        # 🔴 THE TICK SIZE FOLLOWS THE INSTRUMENT'S MEASURED COST PROFILE when the run has one.
        # The config default is gold's 0.01, and SOS Fade prices slippage as ticks x tick size,
        # so a GBPJPY run (tick 0.001) left on the default would be charged ten times its real
        # slippage. This bot exists to run on other instruments, so it cannot rely on a reader
        # remembering to edit a foundational field. With no profile nothing reads the tick
        # here: the stop buffer is pinned to 0 and the trade closes whole at its one target.
        tick = getattr(cost_profile, "mintick", None)
        if tick:
            inner = dataclasses.replace(inner, mintick=float(tick))
        super().__init__(inner, initial_capital=initial_capital, tick_source=tick_source,
                         cost_profile=cost_profile, account=account, leg=leg)
