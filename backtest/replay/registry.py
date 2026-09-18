"""Which python packages declare a `LAB_STRATEGY`, in ONE place.

Every tool that wants to replay a strategy by NAME needs this map, and before this module
existed each one carried its own copy. `backtest/tools/run_report.py` had four entries and
the extreme leg was missing from all of them, so a bot that had been live for a week could
not be named on the command line of the repo's own report tool.

⚠ **Being in this map means the package declares the contract, NOT that every tool can drive
it.** The contract is open on purpose (see `build.py`), so strategies differ in shape: the
SOS Fade family exposes a per-bar decision log and a setup population, the extreme leg does
not. A tool whose REPORTING depends on a shape only some strategies have must narrow this
map to the ones it can honestly report on, rather than offering a name that crashes halfway
through a two-hour replay.
"""

from __future__ import annotations

__all__ = ["STRATEGIES", "load"]

#: strategy name on a command line -> the package that declares its `LAB_STRATEGY`
STRATEGIES: dict[str, str] = {
    "sos_fade": "strategies.python.sos_fade",
    "b_leg": "strategies.python.b_leg",
    "realign": "strategies.python.realign",
    "extreme_leg": "strategies.python.extreme_leg",
}


def load(name: str):
    """Return the named package's `LAB_STRATEGY` dict."""
    import importlib

    if name not in STRATEGIES:
        raise KeyError(f"no strategy named {name!r}. Known: {', '.join(sorted(STRATEGIES))}")
    return importlib.import_module(STRATEGIES[name]).LAB_STRATEGY
