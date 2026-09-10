"""Reconciling what the box is logged into against the account list somebody typed.

The rules under test are all versions of one idea: **the box and the list are two different kinds
of claim, and the interesting output is where they disagree.** So the tests care most about the
three ways this could go quietly wrong —

  * a scan that could not RUN being rendered as a box with no terminals on it,
  * a terminal that could not be ASKED being reported as a contradiction, which fills the page
    with false alarms and teaches everyone to ignore the real one,
  * a real contradiction being smoothed over into agreement.

The live case in `test_a_terminal_on_a_different_account_contradicts_the_row` is not hypothetical:
the account list claimed a terminal for 700107749 that is not logged into it, and that row had been
wrong for weeks with nothing able to notice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest
from services.terminal_scan import (
    ScanUnavailable,
    parse_scan,
    reconcile,
    suggested_registration,
)


@dataclass
class _Row:
    """Stands in for a registry entry — only its attributes are ever read."""

    account: int
    label: str = ""
    server: str = ""
    kind: str = "demo"
    mt5_path: str = ""
    symbol_suffix: Optional[str] = None


def _scan(*terminals, asked=True, **extra):
    return {
        "asked": asked,
        "scanned_at": "2026-09-10T05:00:00Z",
        "terminals": list(terminals),
        **extra,
    }


def _probed(**kw):
    base = {
        "key": r"c:\mt5_scalper",
        "install": r"C:\MT5_Scalper",
        "state": "probed",
        "running": True,
        "owned_by_bots": [],
        "account": 34957946,
        "server": "PUPrime-Live",
        "kind": "live",
        "company": "PU Prime Ltd",
        "symbol_suffix": ".p",
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------------------
# "could not ask" must never render as "nothing there"
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("payload", [None, [], "", {}, {"terminals": []}, 0])
def test_an_unreadable_payload_raises_rather_than_looking_like_an_empty_box(payload):
    """Watched red by defaulting `asked` to True: every one of these then reports a clean scan
    of zero terminals, which is what a truncated pipe or an SSH banner actually looks like."""
    with pytest.raises(ScanUnavailable):
        parse_scan(payload)


def test_a_refused_scan_keeps_its_reason_and_reports_no_verdicts():
    st = parse_scan({"asked": False, "reason": "no instance directory - refusing to scan"})
    assert st.asked is False
    assert "refusing to scan" in st.reason
    assert st.terminals == [] and st.registry == []


def test_a_refused_scan_does_not_judge_the_account_list():
    """A refusal must not mark every registered row unverified — that reads as a finding."""
    out = reconcile({"asked": False, "reason": "box unreachable"}, [_Row(account=700152905)])
    assert out.asked is False
    assert out.registry == []


# ---------------------------------------------------------------------------------------
# Finding an account nobody registered
# ---------------------------------------------------------------------------------------


def test_an_account_the_list_has_never_heard_of_is_new():
    """The whole feature, in one assertion."""
    out = reconcile(_scan(_probed()), [])
    (t,) = out.terminals
    assert t.verdict == "new"
    assert t.actionable is True
    assert t.is_live is True
    assert out.new_accounts == [t]


def test_a_registered_account_the_box_agrees_with_is_not_reported_as_new():
    row = _Row(
        account=34957946,
        server="PUPrime-Live",
        kind="live",
        mt5_path=r"C:\MT5_Scalper\terminal64.exe",
        symbol_suffix=".p",
    )
    out = reconcile(_scan(_probed()), [row])
    (t,) = out.terminals
    assert t.verdict == "known"
    assert t.conflicts == []
    assert [r.verdict for r in out.registry] == ["confirmed"]


def test_an_unestablished_account_mode_is_not_live_and_not_demo():
    """`kind: null` means the broker did not say. It must not read as either answer."""
    out = reconcile(_scan(_probed(kind=None)), [])
    (t,) = out.terminals
    assert t.is_live is False
    assert t.kind is None


# ---------------------------------------------------------------------------------------
# Disagreement
# ---------------------------------------------------------------------------------------


def test_a_demo_row_for_a_live_account_conflicts_and_says_so_plainly():
    """The one that decides whether real money is involved."""
    row = _Row(
        account=34957946,
        kind="demo",
        server="PUPrime-Live",
        mt5_path=r"C:\MT5_Scalper\terminal64.exe",
        symbol_suffix=".p",
    )
    out = reconcile(_scan(_probed()), [row])
    (t,) = out.terminals
    assert t.verdict == "conflict"
    assert any("LIVE" in c for c in t.conflicts)
    assert out.contradicted and out.contradicted[0].account == 34957946


def test_a_server_mismatch_conflicts():
    row = _Row(
        account=34957946,
        server="PUPrime-Demo",
        kind="live",
        mt5_path=r"C:\MT5_Scalper\terminal64.exe",
        symbol_suffix=".p",
    )
    (t,) = reconcile(_scan(_probed()), [row]).terminals
    assert t.verdict == "conflict"
    assert any("PUPrime-Demo" in c and "PUPrime-Live" in c for c in t.conflicts)


def test_a_suffix_mismatch_conflicts_and_an_empty_suffix_is_a_real_claim():
    """`""` means this broker quotes bare symbols — a claim that can be wrong, not an absence."""
    row = _Row(
        account=34957946,
        server="PUPrime-Live",
        kind="live",
        mt5_path=r"C:\MT5_Scalper\terminal64.exe",
        symbol_suffix="",
    )
    (t,) = reconcile(_scan(_probed()), [row]).terminals
    assert t.verdict == "conflict"
    assert any("(nothing)" in c for c in t.conflicts)


def test_an_unrecorded_suffix_is_not_a_conflict():
    """Watched red by treating `None` as a value: an incomplete row then reads as a wrong one,
    and the real disagreements drown."""
    row = _Row(
        account=34957946,
        server="PUPrime-Live",
        kind="live",
        mt5_path=r"C:\MT5_Scalper\terminal64.exe",
        symbol_suffix=None,
    )
    (t,) = reconcile(_scan(_probed()), [row]).terminals
    assert t.verdict == "known"


def test_finding_an_account_on_a_second_terminal_is_not_evidence_against_the_row():
    """🔴 The false alarm the first live run produced, against the one CORRECT row in the list.

    An account can be logged in on several terminals at once, and on this box that is the normal
    state: the demo account is open in the bots' terminal and in the lab's simultaneously. The
    first version compared the row's terminal against wherever the account happened to be found
    and reported a contradiction — so the single row that was entirely right was the only row
    flagged. **A false alarm on the correct row is worse than silence: it is what teaches somebody
    to scroll past the real one.**

    Watched red by restoring that comparison.
    """
    row = _Row(
        account=700152905,
        server="PUPrime-Demo",
        kind="demo",
        mt5_path=r"C:\MT5_FFT\terminal64.exe",
        symbol_suffix=".p",
    )
    payload = _scan(
        {
            "key": r"c:\mt5_fft",
            "install": r"C:\MT5_FFT",
            "state": "owned_by_bot",
            "running": True,
            "owned_by_bots": ["sos_fade_demo"],
            "account": None,
            "reason": "a bot trades through this terminal",
        },
        _probed(
            key=r"c:\mt5_lab",
            install=r"C:\MT5_Lab",
            account=700152905,
            server="PUPrime-Demo",
            kind="demo",
        ),
    )
    out = reconcile(payload, [row])
    lab = [t for t in out.terminals if t.install == r"C:\MT5_Lab"][0]
    assert lab.verdict == "known"
    assert lab.conflicts == []
    (check,) = out.registry
    assert check.verdict == "unverified", "the claimed terminal is a bot's, so it cannot be asked"


def test_the_claimed_terminal_being_on_another_account_is_what_contradicts_a_row():
    """The row's terminal claim is judged by asking THAT terminal, and nothing else can."""
    row = _Row(account=700107749, mt5_path=r"C:\MT5_Scalper\terminal64.exe")
    (check,) = reconcile(_scan(_probed()), [row]).registry
    assert check.verdict == "contradicted"
    assert "34957946" in check.detail


def test_a_confirmed_row_says_where_else_the_account_is_open():
    """Useful rather than alarming: two terminals on one account is worth SEEING, not flagging."""
    row = _Row(
        account=34957946,
        server="PUPrime-Live",
        kind="live",
        mt5_path=r"C:\MT5_Scalper\terminal64.exe",
        symbol_suffix=".p",
    )
    payload = _scan(
        _probed(),
        _probed(key=r"c:\mt5_lab", install=r"C:\MT5_Lab"),
    )
    (check,) = reconcile(payload, [row]).registry
    assert check.verdict == "confirmed"
    assert "also open in" in check.detail and "MT5_Lab" in check.detail


def test_a_terminal_on_a_different_account_contradicts_the_row():
    """🔴 The live defect: a row claiming a terminal that is logged into something else.

    The terminal WAS probed, so this is a measurement rather than a gap, and it must not be
    softened into "unverified".
    """
    row = _Row(account=700107749, label="retired", mt5_path=r"C:\MT5_Scalper\terminal64.exe")
    out = reconcile(_scan(_probed()), [row])
    (check,) = out.registry
    assert check.verdict == "contradicted"
    assert "34957946" in check.detail


# ---------------------------------------------------------------------------------------
# Not being able to check a row is NOT a finding against it
# ---------------------------------------------------------------------------------------


def test_a_row_whose_terminal_a_bot_owns_is_unverified_not_wrong():
    row = _Row(account=700152905, mt5_path=r"C:\MT5_FFT\terminal64.exe")
    payload = _scan(
        {
            "key": r"c:\mt5_fft",
            "install": r"C:\MT5_FFT",
            "state": "owned_by_bot",
            "running": True,
            "owned_by_bots": ["sos_fade_demo"],
            "account": None,
            "reason": "a bot trades through this terminal",
        }
    )
    (check,) = reconcile(payload, [row]).registry
    assert check.verdict == "unverified"
    assert "bot trades through" in check.detail


def test_a_row_whose_terminal_is_stopped_is_unverified():
    row = _Row(account=999, mt5_path=r"C:\Program Files\MetaTrader 5\terminal64.exe")
    payload = _scan(
        {
            "key": r"c:\program files\metatrader 5",
            "install": r"C:\Program Files\MetaTrader 5",
            "state": "not_running",
            "running": False,
            "owned_by_bots": [],
            "account": None,
            "reason": "no terminal process",
        }
    )
    (check,) = reconcile(payload, [row]).registry
    assert check.verdict == "unverified"
    assert "not running" in check.detail


def test_a_row_naming_a_terminal_the_box_does_not_have_is_unverified():
    row = _Row(account=999, mt5_path=r"C:\MT5_Ghost\terminal64.exe")
    (check,) = reconcile(_scan(_probed()), [row]).registry
    assert check.verdict == "unverified"
    assert "no terminal installed" in check.detail


def test_a_row_naming_no_terminal_at_all_is_unverified():
    (check,) = reconcile(_scan(_probed()), [_Row(account=999, mt5_path="")]).registry
    assert check.verdict == "unverified"
    assert "names no terminal" in check.detail


def test_a_terminal_with_no_account_is_never_given_a_verdict():
    payload = _scan(
        {
            "key": r"c:\mt5_lab",
            "install": r"C:\MT5_Lab",
            "state": "probed",
            "running": True,
            "owned_by_bots": [],
            "account": None,
            "error": "attached, but no account",
        }
    )
    (t,) = reconcile(payload, []).terminals
    assert t.verdict == "unasked"
    assert t.actionable is False


# ---------------------------------------------------------------------------------------
# What a discovered account arrives with
# ---------------------------------------------------------------------------------------


def test_a_suggested_registration_fills_only_what_the_box_measured():
    """Watched red by pre-filling a cost profile: it prices every backtest on that account, and
    an unmeasured cost is refused here rather than borrowed from a sibling."""
    out = reconcile(_scan(_probed()), [])
    s = suggested_registration(out.terminals[0])
    assert s["account"] == 34957946
    assert s["server"] == "PUPrime-Live"
    assert s["kind"] == "live"
    assert s["symbol_suffix"] == ".p"
    assert s["broker"] == "PU Prime Ltd"
    assert s["mt5_path"] == r"C:\MT5_Scalper\terminal64.exe"
    assert s["label"] == "" and s["tier"] == "" and s["account_profile"] == "" and s["note"] == ""


def test_a_suggested_registration_carries_no_password_field():
    """The terminal encrypts it at rest, so it cannot be discovered — and a key that is present
    and empty reads as "there is no password", which is a different claim."""
    s = suggested_registration(reconcile(_scan(_probed()), []).terminals[0])
    assert not any("password" in k.lower() for k in s)


def test_an_unmeasured_suffix_stays_none_rather_than_becoming_empty():
    """`""` would tell a move to strip the suffix off a live symbol."""
    s = suggested_registration(reconcile(_scan(_probed(symbol_suffix=None)), []).terminals[0])
    assert s["symbol_suffix"] is None


# ---------------------------------------------------------------------------------------
# The one terminal this tool refuses to attach to, checked via the bots on it
# ---------------------------------------------------------------------------------------


_OWNED = {
    "key": r"c:\mt5_fft",
    "install": r"C:\MT5_FFT",
    "state": "owned_by_bot",
    "running": True,
    "owned_by_bots": ["extreme_leg_demo", "sos_fade_demo"],
    "account": None,
    "reason": "a bot trades through this terminal, so it was deliberately not attached to",
}


def test_a_bots_terminal_is_resolved_from_what_the_BOTS_observe():
    """🔴 The gap that left a stale row unverifiable for weeks.

    The scan never attaches to the bots' terminal, so nothing could say what it is on. The live
    runner measures exactly that at every poll — it halts on a mismatch — and now reports it, which
    is the only outside evidence about this terminal.
    """
    row = _Row(
        account=700152905,
        server="PUPrime-Demo",
        kind="demo",
        mt5_path=r"C:\MT5_FFT\terminal64.exe",
        symbol_suffix=".p",
    )
    out = reconcile(
        _scan(_OWNED), [row], {"sos_fade_demo": 700152905, "extreme_leg_demo": 700152905}
    )
    (t,) = out.terminals
    assert t.account == 700152905
    assert t.account_source == "bot"
    (check,) = out.registry
    assert check.verdict == "confirmed"
    assert "reported by the bot" in check.detail


def test_the_stale_row_is_finally_CONTRADICTED_rather_than_unverified():
    """🔴 700107749, the row that started this. It claims the bots' terminal; the bots are on
    700152905, so the claim is wrong — and until the runner reported its observed account there
    was no way to say so.

    Watched red by dropping the bot-reported resolution: it falls back to "unverified", which is
    honest and useless.
    """
    row = _Row(account=700107749, label="retired", mt5_path=r"C:\MT5_FFT\terminal64.exe")
    out = reconcile(_scan(_OWNED), [row], {"sos_fade_demo": 700152905})
    (check,) = out.registry
    assert check.verdict == "contradicted"
    assert "700152905" in check.detail
    assert any("bot trading through it reports" in c for c in check.conflicts)


def test_a_bot_that_could_not_ask_contributes_nothing():
    """`None` from a bot is "cannot say", not a vote and not a zero."""
    row = _Row(account=700107749, mt5_path=r"C:\MT5_FFT\terminal64.exe")
    out = reconcile(_scan(_OWNED), [row], {"sos_fade_demo": None, "extreme_leg_demo": None})
    (t,) = out.terminals
    assert t.account is None and t.account_source is None
    (check,) = out.registry
    assert check.verdict == "unverified"
    assert "no bot on it could say" in check.detail


def test_bots_that_DISAGREE_resolve_to_unknown_rather_than_a_guess():
    """One terminal holds one login, so a disagreement means somebody is reporting stale state.
    Picking between them would be inventing a fact about a live terminal."""
    row = _Row(account=700152905, mt5_path=r"C:\MT5_FFT\terminal64.exe")
    out = reconcile(
        _scan(_OWNED), [row], {"sos_fade_demo": 700152905, "extreme_leg_demo": 700107749}
    )
    (t,) = out.terminals
    assert t.account is None
    (check,) = out.registry
    assert check.verdict == "unverified"


def test_a_terminal_this_tool_probed_keeps_its_own_reading():
    """A bot's report may not override a number this tool measured itself."""
    out = reconcile(_scan(_probed()), [], {"sos_fade_demo": 999999})
    (t,) = out.terminals
    assert t.account == 34957946
    assert t.account_source == "terminal"


def test_no_bots_map_at_all_behaves_exactly_as_before():
    """The argument is optional, so an older caller keeps the previous, honest answer."""
    row = _Row(account=700152905, mt5_path=r"C:\MT5_FFT\terminal64.exe")
    (check,) = reconcile(_scan(_OWNED), [row]).registry
    assert check.verdict == "unverified"
