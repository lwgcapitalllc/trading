"""The `backtest/setups.py` contract, as this strategy implements it.

⚠ **These build the REAL strategy objects, not stand-ins.** The defect that made this file
necessary was a test double being more capable than production — recorded four times in this repo,
most recently when every reload test passed against a fake that HAD a `.cfg` the real object
lacked. The forks below are the actual `BLegExecution` / `BosExecution` classes.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.setups import implements_contract  # noqa: E402


def _strategy():
    from strategies.python.mpc_sos_fade import LAB_STRATEGY

    cfg = LAB_STRATEGY["config"](fill_model="bar", symbol="XAUUSD")
    return LAB_STRATEGY["strategy"](config=cfg, initial_capital=10_000.0)


# ── the A+ bot, which really does implement it ───────────────────────────────────────────────
def test_the_live_bot_implements_the_contract():
    assert implements_contract(_strategy().execution) is True


def test_a_fresh_execution_is_watching_nothing_and_says_so_with_an_empty_LIST():
    """`[]` here is a real answer — nothing is being watched yet. It is only wrong when it comes
    from an object that could never answer, which is what `reports_setups` separates."""
    assert _strategy().execution.live_setups() == []


def test_the_snapshot_is_labelled_with_the_STRATEGY_name_not_the_execution_class():
    """`mpc_bleg` and `mpc_bos` share this execution layer, so `type(self).__name__` labelled all
    three "Execution" in Telegram — a message naming no bot in a group that will hold several.

    RED against dropping the assignment in `MpcSosFadeStrategy.__init__`.
    """
    assert _strategy().execution.strategy_name == "MpcSosFadeStrategy"


def _real_context(ex, is_long=True):
    """A context built by the REAL `_setup_context`, never hand-written.

    ⚠ **The first version of this file hand-built the dict, and it broke the day `tradeable` was
    added** — a hand-written fixture is a SECOND definition of the shape, and this repo has
    already been bitten four times by a test double that did not match production. Going through
    the real builder means a new key cannot silently bypass the tests that depend on it.
    """
    from types import SimpleNamespace

    from strategies.python.mpc_sos_fade.execution import _MissWatch

    # ⚠ `low` / `high` are the BAR EXTREMES `_announce_ready` reads, and their absence is what
    # this fixture got wrong the day that method landed — the SAME defect this file's docstring
    # warns about, arriving from the opposite direction: a double LESS capable than production
    # rather than more. It failed loudly (AttributeError), which is the good version of it; the
    # dangerous version is a double that answers.
    #
    # The leg is ash 105 / asl 90, so on a long the 0.236 level sits at 101.46. These extremes
    # sit ABOVE it deliberately, so the default context is NOT yet announce-ready and a test
    # that wants the other state has to say so.
    sig = SimpleNamespace(fibo_p2=100.0, fibo_p3=98.0, fibo_p4=97.0, fibo_p5=96.0,
                          fibo_p6=95.0, fibo_p10=94.0, fibo_dir=1 if is_long else -1,
                          fibo_ash=105.0, fibo_asl=90.0,
                          low=102.5 if is_long else 91.0,
                          high=104.0 if is_long else 93.5)
    m = _MissWatch()
    m.open(sos_bar=7, arm_src="SWP", swp_nm="Day Low")
    return ex._setup_context(sig, m, is_long, arm_swp=True, arm_div=False,
                             veto=False, late=False, htf_any=False)


def test_drain_clears_resolved_setups_so_they_are_not_re_sent_every_bar():
    """RED against `drain_setups` returning `live_setups()` without clearing `_setup_done` — the
    live runner calls it once per bar, so a terminal snapshot would repeat for the life of the
    process."""
    from backtest.setups import DEAD

    ex = _strategy().execution
    ex._setup_ctx[0] = _real_context(ex)
    ex._book_setup_end(ex._setup_ctx[0], DEAD, "died")
    assert len(ex.drain_setups()) == 2      # the terminal one + the still-live slot 0
    assert ex._setup_done == []


def test_the_context_carries_every_key_the_snapshot_builders_read():
    """Derives the requirement from the REAL builder rather than restating it, so adding a field
    to `_setup_context` without threading it into both snapshot paths fails here.

    This is the guard that would have caught `tradeable` arriving without its test fixture.
    """
    ex = _strategy().execution
    ctx = _real_context(ex)
    ex._setup_ctx[0] = ctx
    live = ex.live_setups()                     # reads ctx through the WATCHING path
    ex._book_setup_end(ctx, "dead", "died")     # ...and through the terminal path
    assert live and ex._setup_done               # neither raised a KeyError
    assert live[0].tradeable is True


def test_booking_a_terminal_setup_with_no_context_is_dropped_rather_than_raising():
    """A watch opened before this bar's context existed (a warm-up boundary, a restart) has no
    setup the reader was ever told about, so there is nothing to close. It must not raise — this
    runs inside the live bar loop."""
    from backtest.setups import DEAD

    ex = _strategy().execution
    ex._book_setup_end(None, DEAD, "died")
    assert ex._setup_done == []


# ── the forks, which must NOT claim a channel they cannot fill ───────────────────────────────
def test_the_BLEG_fork_does_NOT_claim_the_contract_it_inherits():
    """🔴 The failure this rule exists for, and it arrived by INHERITANCE rather than by a literal
    empty dict. `BLegExecution` sets `_records_misses = False`, which gates the one method that
    populates the setup context — so it inherits a `live_setups()` returning `[]` on every bar
    forever. A method-presence check calls that supported, the runner announces "Setup alerts: ON",
    and the channel sends nothing.

    RED against `implements_contract` checking only that the method exists.
    """
    from strategies.python.mpc_bleg import LAB_STRATEGY

    cfg = LAB_STRATEGY["config"](fill_model="bar", symbol="XAUUSD")
    ex = LAB_STRATEGY["strategy"](config=cfg, initial_capital=10_000.0).execution
    assert ex.reports_setups is False
    assert implements_contract(ex) is False


def test_the_BOS_fork_does_NOT_claim_the_contract_either():
    from strategies.python.mpc_bos import LAB_STRATEGY

    cfg = LAB_STRATEGY["config"](fill_model="bar", symbol="XAUUSD")
    ex = LAB_STRATEGY["strategy"](config=cfg, initial_capital=10_000.0).execution
    assert ex.reports_setups is False
    assert implements_contract(ex) is False


def test_EVERY_fork_of_this_execution_layer_is_checked_not_just_the_two_we_knew_about():
    """Enumerates the forks rather than naming them, so a strategy added tomorrow is covered.

    ✅ **This is not hypothetical: `mpc_realign` landed on main WHILE this contract was being
    built**, sets `_records_misses = False` like its siblings, and correctly declined the channel
    with nobody editing anything. That is the derivation earning its keep — a per-fork flag would
    have needed the author to know a rule that did not exist when they started.

    Fails by NAME on whichever fork starts claiming a channel it cannot fill.
    """
    import importlib

    claiming = []
    for name in ("mpc_bleg", "mpc_bos", "mpc_realign"):
        spec = importlib.import_module(f"strategies.python.{name}").LAB_STRATEGY
        cfg = spec["config"](fill_model="bar", symbol="XAUUSD")
        ex = spec["strategy"](config=cfg, initial_capital=10_000.0).execution
        # A fork MAY legitimately implement the contract — but only by populating the setup
        # context, which means recording misses. Claiming it without that is the failure.
        if implements_contract(ex) and not ex._records_misses:
            claiming.append(name)
    assert not claiming, (f"{claiming} claim the setup contract but cannot populate it — they "
                          f"would announce 'Setup alerts: ON' for a channel that sends nothing")


def test_reports_setups_is_DERIVED_so_a_new_fork_cannot_forget_it():
    """It tracks `_records_misses` rather than being a flag each subclass must remember to set.
    A fork that forgot the line would acquire a silent, empty signals channel — which is the
    failure, not a smaller version of it."""
    ex = _strategy().execution
    assert ex.reports_setups is True
    ex._records_misses = False
    assert ex.reports_setups is False


# ── announce_resting: WHEN a pending limit is worth telling a human about ────────────────────
def _ctx_at(ex, low, high, is_long=True, sos_bar=7):
    """A real context at a chosen bar extreme, so the 0.236 gate can be driven either way."""
    from types import SimpleNamespace

    from strategies.python.mpc_sos_fade.execution import _MissWatch

    sig = SimpleNamespace(fibo_p2=100.0, fibo_p3=98.0, fibo_p4=97.0, fibo_p5=96.0,
                          fibo_p6=95.0, fibo_p10=94.0, fibo_dir=1 if is_long else -1,
                          fibo_ash=105.0, fibo_asl=90.0, low=low, high=high)
    m = _MissWatch()
    m.open(sos_bar=sos_bar, arm_src="SWP", swp_nm="Day Low")
    return ex._setup_context(sig, m, is_long, arm_swp=True, arm_div=False,
                             veto=False, late=False, htf_any=False)


def test_a_limit_is_not_announced_until_price_retraces_to_the_configured_fib():
    """Aaron, 2026-08-14: *"I only want to know a limit is pending when price gets back to 23.6%
    of the retracement."* The ORDER is still placed the moment the setup arms — this gates only
    the message.

    Leg 105/90, so the 0.236 level is 105 - 15*0.236 = 101.46. A bar bottoming at 102.5 has not
    got there; one bottoming at 101.0 has.
    """
    ex = _strategy().execution
    assert _ctx_at(ex, low=102.5, high=104.0)["announce_resting"] is False
    assert _ctx_at(ex, low=101.0, high=104.0)["announce_resting"] is True


def test_the_announcement_LATCHES_so_a_wick_back_out_does_not_un_announce_it():
    """RED against dropping the `_announce_latch_*` write. Without it a setup that dipped to the
    level and recovered would flip back to un-announceable, and the strategy and the alert layer
    would then disagree about why no message was sent."""
    ex = _strategy().execution
    assert _ctx_at(ex, low=101.0, high=104.0)["announce_resting"] is True
    assert _ctx_at(ex, low=103.9, high=104.0)["announce_resting"] is True


def test_a_short_measures_the_retrace_UPWARD():
    """The mirror. A short's leg ran DOWN, so its retrace is price coming back UP and the gate
    reads the bar's HIGH. Reading `low` on both sides would make a short announce instantly —
    plausible on a chart, and wrong."""
    ex = _strategy().execution
    assert _ctx_at(ex, low=90.5, high=92.0, is_long=False)["announce_resting"] is False
    assert _ctx_at(ex, low=90.5, high=94.0, is_long=False)["announce_resting"] is True


def test_the_latch_is_per_LEG_so_a_new_setup_starts_unannounced():
    """Keyed on the SOS bar. A fresh setup inheriting the previous leg's latch would announce
    immediately — the exact behaviour this change exists to remove, restored silently."""
    ex = _strategy().execution
    assert _ctx_at(ex, low=101.0, high=104.0, sos_bar=7)["announce_resting"] is True
    assert _ctx_at(ex, low=102.5, high=104.0, sos_bar=99)["announce_resting"] is False


def test_the_gate_fib_must_stay_SHALLOWER_than_the_entry_band():
    """🔴 The safety property, enforced at construction rather than trusted.

    Every fill is at 0.5 or deeper, so price must cross a shallower level first — which is what
    makes a suppressed message provably a setup that never traded. At 0.5 the guarantee is gone
    and a real trade could reach the trades room unannounced, with nothing reporting the gap.
    """
    import pytest

    from strategies.python.mpc_sos_fade import LAB_STRATEGY

    for bad in (0.5, 0.618, 0.0, -0.1, 1.0):
        with pytest.raises(ValueError, match="alert_resting_fib"):
            LAB_STRATEGY["config"](fill_model="bar", symbol="XAUUSD", alert_resting_fib=bad)
    LAB_STRATEGY["config"](fill_model="bar", symbol="XAUUSD", alert_resting_fib=0.382)
