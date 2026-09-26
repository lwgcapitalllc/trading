"""How big one PIP is on an instrument, in price units — so the chart can state a move in pips.

A pip is a quoting CONVENTION, not a property of the price feed, which is why it cannot be read
off the candles and why this module answers only for instruments whose convention is settled:

  - **Gold (`XAU…`) = 0.10.** The convention PU Prime publishes its gold spreads in ("3.0 pips" on
    Standard is the measured 0.32), and the one `backtest/fills.py` and
    `backtest/tools/killzone_reversal.py` already read gold's pips in. ⚠ Some venues call 0.01 a
    gold pip; a figure quoted off this chart is in PU Prime's unit, a tenth of a dollar.
  - **A forex pair = 0.0001, or 0.01 when JPY is the quote currency.** Universal.

🔴 **Everything else is `None`, and `None` means UNKNOWN — never zero, never a guess** (rule 1,
rule 4). Silver, indices, crypto and futures have no single pip convention (futures quote TICKS),
and a made-up size would print a confident, wrong number on every chip. The chart shows no pip
reading at all for them, which is the honest answer.
"""

from __future__ import annotations

import re
from typing import Optional

#: ISO codes a 6-letter symbol must be built from to count as a forex pair. Without this, any
#: six-letter share or index ticker would be read as a currency pair and handed 0.0001.
_CURRENCIES = frozenset(
    "USD EUR GBP JPY AUD NZD CAD CHF SEK NOK DKK SGD HKD ZAR MXN TRY PLN CNH HUF CZK".split()
)

_GOLD_PIP = 0.10
_FX_PIP = 0.0001
_JPY_PIP = 0.01


def _core(instrument: str) -> str:
    """The symbol without its broker suffix — `XAUUSD.p` → `XAUUSD`, `EURUSD.s` → `EURUSD`."""
    return re.split(r"[^A-Za-z0-9]", instrument or "", maxsplit=1)[0].upper()


def pip_size(instrument: str) -> Optional[float]:
    """One pip in price units, or `None` when the instrument has no settled convention."""
    sym = _core(instrument)
    if sym.startswith("XAU"):
        return _GOLD_PIP
    if len(sym) == 6 and sym[:3] in _CURRENCIES and sym[3:] in _CURRENCIES:
        return _JPY_PIP if sym[3:] == "JPY" else _FX_PIP
    return None
