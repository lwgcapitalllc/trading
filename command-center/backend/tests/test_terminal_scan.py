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
    assert "Also open on" in check.detail and "MT5_Lab" in check.detail


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
    assert "your bots' terminal" in check.detail


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
    assert "No terminal is recorded" in check.detail


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
    assert any("reported by the bot there" in c and "MT5_FFT" in c for c in check.conflicts)


def test_a_bot_that_could_not_ask_contributes_nothing():
    """`None` from a bot is "cannot say", not a vote and not a zero."""
    row = _Row(account=700107749, mt5_path=r"C:\MT5_FFT\terminal64.exe")
    out = reconcile(_scan(_OWNED), [row], {"sos_fade_demo": None, "extreme_leg_demo": None})
    (t,) = out.terminals
    assert t.account is None and t.account_source is None
    (check,) = out.registry
    assert check.verdict == "unverified"
    assert "no bot on it has reported" in check.detail


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


def test_no_sentence_a_person_reads_carries_a_raw_windows_path():
    """🔴 Aaron, 2026-09-10, looking at this panel: *"I don't know what I'm looking at."*

    The first wording put full Windows paths into sentences — *"this row claims
    C:\\MT5_FFT\\terminal64.exe"* — which reads as a log line, not an answer. Every detail and
    conflict now names a terminal by its folder, the name it goes by on the box.

    Watched red against the previous wording: `terminal64.exe` appears in three of these strings.
    """
    rows = [
        _Row(account=700107749, mt5_path=r"C:\MT5_FFT\terminal64.exe"),
        _Row(
            account=700152905,
            server="PUPrime-Demo",
            kind="demo",
            mt5_path=r"C:\MT5_Lab\terminal64.exe",
            symbol_suffix=".p",
        ),
        _Row(account=111, mt5_path=r"C:\MT5_Ghost\terminal64.exe"),
        _Row(account=222, mt5_path=r"C:\Program Files\MetaTrader 5\terminal64.exe"),
    ]
    payload = _scan(
        _OWNED,
        _probed(
            key=r"c:\mt5_lab",
            install=r"C:\MT5_Lab",
            account=700152905,
            server="PUPrime-Demo",
            kind="demo",
        ),
        {
            "key": r"c:\program files\metatrader 5",
            "install": r"C:\Program Files\MetaTrader 5",
            "state": "not_running",
            "running": False,
            "owned_by_bots": [],
            "account": None,
        },
    )
    out = reconcile(payload, rows, {"sos_fade_demo": 700152905})
    said = [r.detail for r in out.registry] + [c for r in out.registry for c in r.conflicts]
    assert said, "the fixture must produce sentences to check"
    for sentence in said:
        assert "terminal64.exe" not in sentence, sentence
        assert ":\\" not in sentence, sentence


# ---------------------------------------------------------------------------------------
# A row with NO terminal is offered the one the box found it on — when nothing else uses it
# ---------------------------------------------------------------------------------------

_PU_PRIME = {
    "key": r"c:\program files\pu prime mt5 terminal",
    "install": r"C:\Program Files\PU Prime MT5 Terminal",
    "state": "probed",
    "running": True,
    "owned_by_bots": [],
    "account": 35710389,
    "server": "PUPrime-Live",
    "kind": "live",
    "symbol_suffix": ".p",
}
_PU_PRIME_EXE = r"C:\Program Files\PU Prime MT5 Terminal\terminal64.exe"


def _new_live_row(**kw):
    return _Row(account=35710389, server="PUPrime-Live", kind="live", symbol_suffix=".p", **kw)


def test_a_row_with_no_terminal_is_offered_the_one_it_is_logged_into():
    """🔴 Aaron, 2026-09-13: *"When I hit scan VPS, you already know all the information. Why do I
    have to put it in?"* The scan had found 35710389 on this terminal and the form still opened
    empty — and the path typed by hand was the demo bots' terminal.

    Watched red by returning no suggestion from the no-terminal branch."""
    (check,) = reconcile(_scan(_PU_PRIME), [_new_live_row()]).registry
    assert check.suggested_terminal == _PU_PRIME_EXE
    assert "PU Prime MT5 Terminal" in check.terminal_note
    # A SUGGESTION, not a verdict: the row stays unverified until somebody saves a terminal.
    assert check.verdict == "unverified"


def test_a_terminal_ANOTHER_ACCOUNT_uses_is_never_offered():
    """The case that nearly happened: a terminal another account's bots depend on, offered to a
    new account. A bot added there would log that terminal into this account and off the other.

    Watched red by dropping the claimed-terminal check."""
    rows = [_new_live_row(), _Row(account=700152905, mt5_path=r"C:\MT5_Scalper\terminal64.exe")]
    payload = _scan(_probed(account=35710389))  # MT5_Scalper, logged into the new account
    check = next(c for c in reconcile(payload, rows).registry if c.account == 35710389)
    assert check.suggested_terminal is None
    assert "700152905" in check.terminal_note


def test_the_labs_backtest_terminal_is_never_offered():
    """The tier-probe accounts were logged into MT5_Lab for minutes and deliberately left with no
    terminal: a bot pointed there would trade through the terminal the backtests run on.

    Watched red by dropping the lab check."""
    payload = _scan(_probed(key=r"c:\mt5_lab", install=r"C:\MT5_Lab", account=35710389))
    (check,) = reconcile(payload, [_new_live_row()]).registry
    assert check.suggested_terminal is None
    assert "backtest" in check.terminal_note


def test_the_bots_own_terminal_is_never_offered():
    """A bots' terminal holds one login and those bots trade it. Watched red by dropping the
    owned-by-bots check."""
    out = reconcile(
        _scan(dict(_OWNED)),
        [_new_live_row()],
        {"sos_fade_demo": 35710389, "extreme_leg_demo": 35710389},
    )
    (check,) = out.registry
    assert check.suggested_terminal is None
    assert "your bots trade through" in check.terminal_note


def test_two_free_terminals_are_named_and_neither_is_picked():
    """One account open in two free terminals is a choice about where its bots run — the person's,
    never a pick made here. Watched red by taking the first free terminal."""
    other = dict(_PU_PRIME, key=r"c:\mt5_spare", install=r"C:\MT5_Spare")
    (check,) = reconcile(_scan(_PU_PRIME, other), [_new_live_row()]).registry
    assert check.suggested_terminal is None
    assert "MT5_Spare" in check.terminal_note
    assert "PU Prime MT5 Terminal" in check.terminal_note


def test_a_free_terminal_is_still_offered_when_a_barred_one_also_holds_the_account():
    """An account open in the lab AND one free terminal is normal here. Barring the lab must still
    leave the free one — a rule that gave up on any barred sighting would offer nothing."""
    lab = _probed(key=r"c:\mt5_lab", install=r"C:\MT5_Lab", account=35710389)
    (check,) = reconcile(_scan(lab, _PU_PRIME), [_new_live_row()]).registry
    assert check.suggested_terminal == _PU_PRIME_EXE


def test_a_row_that_already_HAS_a_terminal_is_offered_nothing():
    """Only an EMPTY terminal is filled in. Offering another on a row that has one would read as a
    correction, and which terminal a row uses is the person's call."""
    row = _new_live_row(mt5_path=r"C:\MT5_Scalper\terminal64.exe")
    (check,) = reconcile(_scan(_PU_PRIME), [row]).registry
    assert check.suggested_terminal is None
    assert check.terminal_note == ""


def test_an_account_the_box_found_nowhere_gets_no_note():
    """No terminal it could ask holds the account: say nothing rather than guess a reason."""
    (check,) = reconcile(_scan(_probed()), [_new_live_row()]).registry
    assert check.suggested_terminal is None
    assert check.terminal_note == ""


def test_the_note_names_terminals_by_their_folder_never_a_raw_path():
    """Same rule as every sentence above. The PATH travels in its own field, for the form."""
    rows = [_new_live_row(), _Row(account=700152905, mt5_path=r"C:\MT5_Scalper\terminal64.exe")]
    notes = [
        c.terminal_note
        for payload in (_scan(_PU_PRIME), _scan(_probed(account=35710389)))
        for c in reconcile(payload, rows).registry
    ]
    assert any(notes), "the fixture must produce notes to check"
    for note in notes:
        assert "terminal64.exe" not in note, note
        assert ":\\" not in note, note


def test_the_lab_terminal_is_the_one_the_agent_binds():
    """`_LAB_KEYS` is a COPY of the lab's install path — this backend cannot import the agent. So
    this reads the agent's source and fails when its baked-in lab path moves, rather than letting
    the lab's terminal quietly become one the form would offer."""
    from pathlib import Path

    from services.terminal_scan import _LAB_KEYS, _install_key

    agent = (
        Path(__file__).resolve().parents[3] / "algos" / "markets" / "fx" / "tools" / "mt5_agent.py"
    )
    assert 'Path(r"C:\\MT5_Lab")' in agent.read_text(encoding="utf-8"), (
        "the agent no longer binds C:\\MT5_Lab"
    )
    assert _install_key(r"C:\MT5_Lab\terminal64.exe") in _LAB_KEYS
