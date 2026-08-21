"""The pins where this fork DELIBERATELY disagrees with its A+ parent.

A pin here is never tidiness — it is a written-down record that `mpc_b_leg_strategy.pine` and
`mpc_strategy.pine` genuinely differ on some input. Without it the fork silently inherits whatever
the parent's default becomes, and the two Pines drift apart with nothing failing.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mpc_bleg import MpcBLegStrategy  # noqa: E402
from mpc_sos_fade import MpcSosFadeStrategy  # noqa: E402


def test_the_fork_pins_the_eq_fvg_coupling_OFF_where_the_parent_pins_it_ON():
    """`eqExemptFvg` is `true` in `mpc_strategy.pine` and `false` in `mpc_b_leg_strategy.pine`.

    The coupling decides which gaps survive the FVG cap, so it decides which entries fire. This
    fork does NOT override `_entry_edges`, and those A+ edges feed the "A+ has priority, stand the
    B leg down" gate — so inheriting the parent's ON would move B-LEG trades with no Pine change
    behind it, and put `compare_bleg.py` red against this fork's own export.

    Same shape as the `exec_min_stop_mode = "Off"` pin in `config.py`. Delete this override only
    in the commit that ports the input into `mpc_b_leg_strategy.pine`, then re-run `compare_bleg.py`.
    """
    assert MpcSosFadeStrategy.engine_config().eq_exempt_fvg is True
    assert MpcBLegStrategy.engine_config().eq_exempt_fvg is False


def test_the_fork_inherits_every_OTHER_engine_pin_from_the_parent():
    """The override must be a one-field delta, never a second copy of the parent's pins.

    A hand-written config here would go stale the moment the parent pins a new engine input — the
    quiet direction, because nothing would fail. Asserting field-by-field equality except the one
    deliberate difference is what keeps the fork a fork.
    """
    import dataclasses

    parent = MpcSosFadeStrategy.engine_config()
    fork = MpcBLegStrategy.engine_config()
    for f in dataclasses.fields(parent):
        if f.name == "eq_exempt_fvg":
            continue
        assert getattr(fork, f.name) == getattr(parent, f.name), (
            f"{f.name} drifted from the parent's pin — the fork must differ on eq_exempt_fvg alone"
        )


def test_the_fork_pins_the_secondary_OFF():
    """The parent defaulted `exec_secondary` ON on 2026-08-07 and this fork cannot honour it.

    The 1m re-entry follows a 15m A+ PRIMARY that reached breakeven, and in this fork A+ never
    places an order — `MpcBLegStrategy.run_dual` raises outright. The lab reads this field to
    decide whether to load a 1m feed and call `run_dual`, so an INHERITED True does not change
    this bot's trades, it kills every B-LEG lab run on a NotImplementedError.

    Watched red against the pin removed."""
    from strategies.python.mpc_bleg.config import BLegConfig
    from strategies.python.mpc_sos_fade.config import SosFadeConfig

    # ⚠ ANSWERING THIS TEST'S OWN QUESTION (2026-08-21): the parent's default WAS deliberately
    # reverted to False — Aaron's call, every optional entry path now ships OFF. So this fork's pin
    # is REDUNDANT rather than load-bearing today.
    #
    # 🔴 It is kept, and the fork's own value below is the point of the test now. A fork that leans
    # on its parent's default is one flip away from breaking, and this field has flipped TWICE (ON
    # 2026-08-07, OFF 2026-08-21). What must stay true is that THIS fork is False whatever the
    # parent does — an inherited True kills every B-LEG lab run on a NotImplementedError, which is
    # a crash rather than a mis-priced trade.
    assert SosFadeConfig().exec_secondary is False, (
        "the parent defaults this ON again — then this fork's pin is LOAD-BEARING once more and "
        "the note above is stale; say which in the same commit")
    assert BLegConfig().exec_secondary is False
