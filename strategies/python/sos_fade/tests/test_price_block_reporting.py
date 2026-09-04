"""The two refusals that depend on PRICE, and the fact that they now SAY SO.

Until 2026-09-03 the minimum-stop floor and the dead-market gate were the only shipped rules
that could refuse a fully-ready setup and report nothing a human would ever see. The floor at
least booked a block record for the lab (code 7); the dead-market gate rode inside
`_stop_clears_floor` and booked nothing anywhere — no block, no miss code, no Telegram message.
Both are ON in the live bot's promoted params, so this was silence on real skipped trades.

⚠ **REPORTING ONLY.** Nothing here may move a decision. The claim that it does not is proved by
REPLAY (a byte-identical trade list over the full history), never by these tests — see
`strategies/python/sos_fade/CLAUDE.md` → *The two price refusals report themselves*.

**Watched RED against HEAD**, and each assertion names what turns it red:
  - the block-code and miss-code cases fail at HEAD because codes 10 / 8 / 9 do not exist there;
  - `_price_blocks` does not exist at HEAD, so every case reading it fails at attribute lookup;
  - the `blocked_by` cases return the three-toggle list at HEAD and fail on the missing entry.
Because "the code is new" cannot tell a working rule from a present one, the behavioural
guarantees are ALSO pinned by mutation — each docstring below names the mutation that reddens it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from strategies.python.sos_fade.config import SosFadeConfig  # noqa: E402
from strategies.python.sos_fade.execution import (  # noqa: E402
    _BLOCK_LABEL,
    _BLOCK_REASON,
    _MISS_LABEL,
    _MISS_REASON,
    Execution,
    MissedSetup,
    _block_codes,
    _MissWatch,
)


def _sig(is_long=True):
    """The same leg the setup-contract fixture uses: ash 105 / asl 90, stop anchor 0.886 = 95."""
    return SimpleNamespace(
        fibo_p2=100.0, fibo_p3=98.0, fibo_p4=97.0, fibo_p5=96.0, fibo_p6=95.0, fibo_p10=94.0,
        fibo_dir=1 if is_long else -1, fibo_ash=105.0, fibo_asl=90.0,
        low=102.5 if is_long else 91.0, high=104.0 if is_long else 93.5,
    )


def _ex(atr=5.0, **cfg_kw):
    ex = Execution(SosFadeConfig(**cfg_kw))
    ex._atr = atr
    return ex


# ── the shared helper: one implementation, three readers ─────────────────────────────────────
def test_a_healthy_setup_is_refused_by_NEITHER_price_rule():
    """The control. Edge 100 against a 0.886 anchor at 95 is a $5 stop, miles clear of the 0.08%
    floor ($0.08), and ATR 5.0 on price 100 is 5% against a 0.08% floor.

    MUTATION: flip either comparison in `_market_has_range` / `_stop_is_tight` and this reddens.
    """
    assert _ex()._price_blocks(_sig(), 100.0, True) == (False, False)


def test_a_stop_under_the_floor_reports_TIGHT_and_not_quiet():
    """A 10%-of-price floor is $10 against a $5 stop. The market is unchanged, so the second
    flag must stay False — the two rules ask different questions and neither substitutes for
    the other.

    MUTATION: make `_price_blocks` return the same flag twice and the second assertion reddens.
    """
    ex = _ex(exec_min_stop_val=10.0)
    assert ex._price_blocks(_sig(), 100.0, True) == (True, False)


def test_a_dead_market_reports_QUIET_and_not_tight():
    """ATR 0.01 on price 100 is 0.01%, under the 0.08% floor. The stop is untouched at $5.

    MUTATION: drop the `_market_has_range` call from `_price_blocks` and this reddens.
    """
    assert _ex(atr=0.01)._price_blocks(_sig(), 100.0, True) == (False, True)


def test_a_SHORT_measures_its_stop_distance_UPWARD():
    """A short's stop sits ABOVE its entry, so a distance computed with the long's subtraction
    comes back negative and `_stop_is_tight` reads a negative distance as *not* tight — the
    refusal would silently never be reported on shorts.

    Edge 90 against the 0.886 anchor at 95 is a $5 stop; a $10 floor must refuse it.
    MUTATION: use the long branch for both sides and this reddens while the long case stays green.
    """
    ex = _ex(exec_min_stop_val=10.0)
    assert ex._price_blocks(_sig(is_long=False), 90.0, False) == (True, False)


def test_NO_EDGE_answers_neither_rather_than_answering_PASSED():
    """🔴 The rule this repo keeps paying for: never let *no* and *cannot ask* be the same value.

    With nothing to rest a limit on, neither price rule has been REACHED — the setup is stopped a
    step earlier, by something else. Both flags are False so the caller reports nothing, and the
    reader is never told a dead market passed a test it was never given.
    """
    ex = _ex(atr=0.01, exec_min_stop_val=10.0)   # both rules WOULD refuse, given an edge
    assert ex._price_blocks(_sig(), None, True) == (False, False)


def test_an_UNSEEDED_ATR_is_not_reportable_as_a_quiet_market():
    """The gate itself still REFUSES an unseeded ATR — that is `test_dead_market.py`'s subject and
    is unchanged here. What must not happen is the refusal being RENDERED as "market too quiet",
    which is a different sentence and is not true of a bot that has simply not measured yet.

    MUTATION: drop the `self._atr is not None` term and this reddens.
    """
    ex = _ex(atr=None)
    assert ex._market_has_range(100.0) is False        # still refuses the entry
    assert ex._price_blocks(_sig(), 100.0, True)[1] is False   # ...and does not call it quiet


def test_a_missing_fib_leaves_the_stop_UNKNOWN_rather_than_tight():
    """No anchor means no distance to compare, and an unknown distance is not a refusal to
    report. The quiet flag must survive, because it never needed the anchor.

    MUTATION: return `(True, quiet)` on the anchor-less path and this reddens.
    """
    sig = _sig()
    sig.fibo_p6 = None
    ex = _ex(atr=0.01, exec_min_stop_val=10.0)
    assert ex._price_blocks(sig, 100.0, True) == (False, True)


# ── the lab's block record ───────────────────────────────────────────────────────────────────
def test_the_dead_market_gate_finally_HAS_a_block_code():
    """It had none for its whole life, which is why it could refuse a live trade in silence."""
    assert _BLOCK_LABEL[10] == "Market too quiet"
    assert "volatility" in _BLOCK_REASON[10]


def test_the_new_code_is_APPENDED_so_every_existing_primary_is_unmoved():
    """`codes[0]` must stay exactly what the Pine's own reason function would have returned, or a
    per-reason count taken off the primary stops reconciling with TradingView.

    MUTATION: insert `quiet` anywhere but last in `_block_codes` and this reddens.
    """
    assert _block_codes(False, False, True, False, False, False, quiet=True) == [3, 10]
    assert _block_codes(False, False, False, False, False, False, tight=True, quiet=True) \
        == [7, 10]
    assert _block_codes(False, False, False, False, False, False, quiet=True) == [10]


def test_a_quiet_market_alone_does_not_look_like_an_unblocked_setup():
    """An empty code list is what "nothing is refusing this" means, so the dead-market gate had
    to produce a non-empty one or `_record_blocks` would keep skipping the record entirely."""
    assert _block_codes(False, False, False, False, False, False) == []
    assert _block_codes(False, False, False, False, False, False, quiet=True) != []


# ── the miss record, which is the message that actually arrives when a setup dies ────────────
def test_the_two_price_refusals_were_carved_OUT_of_never_filled():
    """🔴 This is a CORRECTION, not an addition. Code 7 claims the limit rested and price never
    came back; for a setup either price rule refused, no limit was ever placed. The reader was
    being told a story about an order that did not exist.

    MUTATION: point codes 8 and 9 back at `_MISS_REASON[7]` and this reddens.
    """
    assert _MISS_LABEL[8] == "Stop too tight"
    assert _MISS_LABEL[9] == "Market too quiet"
    for code in (8, 9):
        assert "rested" not in _MISS_REASON[code]
        assert "no limit was placed" in _MISS_REASON[code]


def test_every_miss_code_can_render_a_label_AND_a_sentence():
    """The alert reuses the miss's own sentence, so a code with a label and no reason sends a
    `NO TRADE` reply naming the label twice. Code 1 composes its sentence dynamically and is
    checked through a real record below."""
    for code in _MISS_LABEL:
        assert _MISS_LABEL[code]
        assert code == 1 or _MISS_REASON[code]


def _miss(code):
    return MissedSetup(dir=1, index=0, time_ms=0, met=3, code=code, arm_text="Sweep",
                       arm_met=True, zone=True, zone_time_ms=None, zone_turn_ms=None,
                       fvg=True, edge=100.0, near=True)


def test_a_dead_market_death_reads_as_a_dead_market_and_not_as_an_unfilled_limit():
    assert _miss(9).labels[0] == "Market too quiet"
    assert "dead market" in _miss(9).reasons[0]
    assert "price never came back" in _miss(7).reasons[0]


# ── the watch that latches them ──────────────────────────────────────────────────────────────
def test_opening_a_watch_CLEARS_both_new_latches():
    """A latch that survives into the next setup reports the previous one's refusal against a
    setup that never met it.

    MUTATION: drop either field from `_MissWatch.open` and this reddens.
    """
    m = _MissWatch()
    m.blk_t = m.blk_q = True
    m.open(sos_bar=1, arm_src="SWP", swp_nm="Day Low")
    assert m.blk_t is False
    assert m.blk_q is False


# ── the Telegram snapshot ────────────────────────────────────────────────────────────────────
def _ctx(ex, tight=False, quiet=False, ready=True):
    m = _MissWatch()
    m.open(sos_bar=7, arm_src="SWP", swp_nm="Day Low")
    if ready:
        m.zone = True
        m.fvg = True
    return ex._setup_context(_sig(), m, True, arm_swp=True, arm_div=False,
                             veto=False, late=False, htf_any=False, tight=tight, quiet=quiet)


def test_a_ready_setup_refused_by_the_stop_floor_SAYS_SO():
    """The whole point of the change. At HEAD this list is empty for the same inputs."""
    assert _ctx(_ex(), tight=True)["blocked_by"] == ("Stop too tight for your minimum",)


def test_a_ready_setup_refused_by_a_dead_market_SAYS_SO():
    assert _ctx(_ex(), quiet=True)["blocked_by"] == ("Market too quiet to fade",)


def test_both_price_rules_are_reported_when_both_refuse():
    """Carrying every refusing rule rather than only the first is what `format_blocked` promises
    — "blocked by the veto" has to stay true on a setup the floor was also blocking."""
    assert _ctx(_ex(), tight=True, quiet=True)["blocked_by"] == (
        "Stop too tight for your minimum", "Market too quiet to fade")


def test_a_setup_still_FORMING_reports_no_price_block():
    """🔴 The existing invariant, and the new rules must not break it. A rule live while a setup
    is merely forming is not what stopped it — reporting that announced setups that went on to
    rest and fill, under a sentence reading "the setup was ready and this rule stopped it".

    MUTATION: hoist the two new appends out of the `arm_met and zone_met` guard and this reddens.
    """
    assert _ctx(_ex(), tight=True, quiet=True, ready=False)["blocked_by"] == ()


def test_the_defaults_keep_a_clean_setup_silent():
    """No refusal, no message. A blocked alert on every setup is a blocked alert nobody reads."""
    assert _ctx(_ex())["blocked_by"] == ()


def test_the_message_the_reader_actually_receives_names_both_rules():
    """Through the REAL formatter, not a hand-written string — the alert layer joins the tuple and
    a change to that join is exactly what a test reading `blocked_by` alone would miss."""
    from backtest.setups import WATCHING, SetupSnapshot

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_alerts_under_test", _ROOT / "algos" / "live" / "alerts.py")
    alerts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(alerts)

    snap = SetupSnapshot(key="k", strategy="SosFadeStrategy", symbol="XAUUSD.p", side=1,
                         state=WATCHING,
                         blocked_by=_ctx(_ex(), tight=True, quiet=True)["blocked_by"])
    text = alerts.format_blocked(snap)
    assert "Stop too tight for your minimum" in text
    assert "Market too quiet to fade" in text


def test_a_caller_that_FORGETS_the_price_flags_fails_loudly():
    """🔴 Rule 10 in miniature: a default of False makes a forgotten argument look exactly like a
    setup nothing is refusing, and the live rule goes quiet with nothing to see.

    MUTATION: give `tight` / `quiet` defaults back in `_setup_context` and this reddens.
    """
    import pytest

    m = _MissWatch()
    m.open(sos_bar=7, arm_src="SWP", swp_nm="Day Low")
    with pytest.raises(TypeError):
        _ex()._setup_context(_sig(), m, True, arm_swp=True, arm_div=False,
                             veto=False, late=False, htf_any=False)
