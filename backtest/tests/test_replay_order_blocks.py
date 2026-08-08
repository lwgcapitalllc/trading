"""EngineStack ↔ order_blocks wiring.

The order-block engine has been canonical and Pine-parity green since 2026-07-31, but until now
its only consumers were the command-center price chart (`services/ob_overlays.py`) and its own
parity harness — nothing in `backtest/replay/` touched it, so no STRATEGY could see a block.
These tests pin the wiring that closed that gap.

What they are actually guarding, in order of how much it would cost to get wrong:

1. **Turning it on changes NOTHING else.** The whole point of an opt-in engine is that every
   existing result stays reproducible. If wiring an engine in perturbed the fibs or the FVG cap,
   every measured figure in this repo would silently move.
2. **Off and empty are different values.** `None` = the engine never ran. An `OrderBlockEvents`
   with empty lists = it ran and found nothing. Collapsing them is the defect this repo has met
   on the live bot's terminal probe, the optimizer's sensitivity score and the news calendar.
3. **It actually drives.** A flag that builds an engine nobody feeds is a flag that does nothing.

Run:  python3 -m pytest backtest/tests/test_replay_order_blocks.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_ENGINES = _ROOT / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

from order_blocks import OrderBlockEngine, OrderBlockEvents  # noqa: E402

from backtest.replay import EngineConfig, EngineStack, iter_bars, run  # noqa: E402
from backtest.tests._synth import synth_bars  # noqa: E402


# --------------------------------------------------------------- default OFF -----
def test_order_blocks_are_off_by_default():
    """No strategy reads a block today, so the default must not make anyone pay for one."""
    stack = EngineStack()
    assert stack.config.order_blocks is False
    assert stack.order_blocks is None


def test_off_reports_none_not_an_empty_events_object():
    """`None` means the question was never asked. An empty OrderBlockEvents would mean the engine
    ran and this bar had nothing — a claim the stack is in no position to make when it never
    built the engine. A strategy reading `.active_bull` off this gets a loud AttributeError
    instead of silently seeing 'no blocks' on every bar and quietly taking no trades."""
    df = synth_bars(3)
    for state in run(df):
        assert state.order_blocks is None


# ---------------------------------------------------------------- default ON -----
def test_on_builds_the_canonical_engine():
    stack = EngineStack(EngineConfig(order_blocks=True))
    assert isinstance(stack.order_blocks, OrderBlockEngine)


def test_on_reports_events_on_every_bar_including_quiet_ones():
    """The counterpart to the None test: once enabled, EVERY bar carries a real events object,
    not just the bars that happened to create or mitigate something. That is what makes `None`
    unambiguous — it can only ever mean 'not enabled'."""
    df = synth_bars(6)
    states = list(run(df, EngineConfig(order_blocks=True)))
    assert len(states) == len(df)
    assert all(isinstance(s.order_blocks, OrderBlockEvents) for s in states)
    # and the series really does contain quiet bars, or this proves nothing
    quiet = [s for s in states if not s.order_blocks.created and not s.order_blocks.mitigated]
    assert quiet, "synthetic series has no quiet bars — the assertion above is vacuous"


def test_the_engine_actually_drives():
    """A flag that constructs an engine nobody feeds is a flag that does nothing."""
    df = synth_bars(12)
    created = mitigated = 0
    live_seen = 0
    for s in run(df, EngineConfig(order_blocks=True)):
        created += len(s.order_blocks.created)
        mitigated += len(s.order_blocks.mitigated)
        live_seen = max(live_seen,
                        len(s.order_blocks.active_bull) + len(s.order_blocks.active_bear))
    assert created > 0, "no order blocks created over 12 days of impulse bars"
    assert mitigated > 0, "blocks were created but none was ever consumed"
    assert live_seen > 0, "no live zone was ever readable off a BarState"


def test_stack_output_matches_a_hand_driven_engine():
    """The stack must not be a second implementation — feeding a bare OrderBlockEngine the same
    closed bars in the same order has to produce the same block ids, bar for bar."""
    df = synth_bars(8)
    stack = EngineStack(EngineConfig(order_blocks=True))
    bare = OrderBlockEngine()

    for bar in iter_bars(df):
        via_stack = stack.step(bar).order_blocks
        direct = bare.update(bar.index, bar.open, bar.high, bar.low, bar.close)
        assert [o.id for o in via_stack.created] == [o.id for o in direct.created]
        assert [o.id for o in via_stack.mitigated] == [o.id for o in direct.mitigated]


# ------------------------------------------------------ the additive guarantee -----
def test_enabling_order_blocks_changes_no_other_engine():
    """THE load-bearing test. Every measured figure in this repo was produced by a stack with no
    order-block engine in it. If switching one on could perturb the structure stream, the fibs,
    the FVG cap or the liquidity levels, none of those numbers would be reproducible any more.

    The OB engine is standalone (plain OHLC in, no snapshot) and nothing downstream reads it, so
    this SHOULD hold by construction — which is exactly the kind of claim worth pinning, because
    'by construction' is how the eq_exempt_fvg coupling got missed for three days.
    """
    df = synth_bars(10)
    fields = ("structure", "snapshot", "fib", "sniper", "macro",
              "internal", "fvg", "rsi", "liquidity", "sessions")

    off = list(run(df))
    on = list(run(df, EngineConfig(order_blocks=True)))
    assert len(off) == len(on) == len(df)

    for a, b in zip(off, on):
        for name in fields:
            assert repr(getattr(a, name)) == repr(getattr(b, name)), (
                f"{name} moved when order blocks were switched on, at bar {a.bar.index}")
        # ...and the only field that DID change is the new one
        assert a.order_blocks is None
        assert b.order_blocks is not None


def test_config_is_not_shared_between_stacks():
    """Two stacks built from one EngineConfig must not share engine state — a sweep builds many."""
    cfg = EngineConfig(order_blocks=True)
    a, b = EngineStack(cfg), EngineStack(cfg)
    assert a.order_blocks is not b.order_blocks
