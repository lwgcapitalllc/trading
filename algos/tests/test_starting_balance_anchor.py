"""`starting_balance` is an anchor for an ACCOUNT, and it used to be stored as if it were one
for a BOT.

🔴 **Written after the anchor survived a move it had no business surviving.** On 2026-08-12
`sos_fade_demo` was moved from the PU Prime Standard demo (anchored at $2,000, grown to
~$10,000) onto the ECN demo, which opens at $10,000. `ensure_starting_balance` wrote once and never
again, so the bot would have carried the old account's $2,000 anchor onto the new one and reported
**+399% on its first poll, for ever** — on the Bots page and in Telegram's `/balance`, the only two
readers of `total_pnl_pct`. Nothing errors, and +399% is exactly the sort of number a bot that has
been running well is expected to show.

⚠ **The migration is ADOPT, never RESET, and that is the judgement call worth defending.** An
anchor written before this field existed carries no account, so *"it belongs to this account"* and
*"it belongs to one this bot has left"* are indistinguishable — and of the two available mistakes,
throwing away a real measurement is worse than keeping one that might be stale. **So this guard
could not have caught the move that motivated it**; the stale anchor was cleared by hand and this
exists so the next move is automatic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
for p in (str(_REPO), str(_REPO / "algos" / "shared")):
    if p not in sys.path:
        sys.path.insert(0, p)

import bot_state  # noqa: E402

BOT = "sos_fade_demo"


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    """Point the module's one registry at a scratch directory. Nothing real is written."""
    monkeypatch.setitem(bot_state.BOT_INSTANCES, BOT, tmp_path)
    return tmp_path


def test_the_first_run_anchors_and_records_which_account_it_anchored_to(isolated):
    bot_state.ensure_starting_balance(BOT, 10_000.0, 700152905)

    s = bot_state.read_bot(BOT)
    assert s["starting_balance"] == 10_000.0
    assert s["starting_balance_account"] == 700152905


def test_a_growing_balance_on_the_same_account_never_moves_the_anchor(isolated):
    """The whole point of the anchor. Re-anchoring here would report every bot as dead flat."""
    bot_state.ensure_starting_balance(BOT, 2_000.0, 700107749)
    bot_state.ensure_starting_balance(BOT, 9_996.99, 700107749)

    assert bot_state.read_bot(BOT)["starting_balance"] == 2_000.0


def test_moving_the_bot_to_another_account_re_anchors(isolated):
    """The defect. Without this the ECN account reports the Standard account's growth."""
    bot_state.ensure_starting_balance(BOT, 2_000.0, 700107749)

    bot_state.ensure_starting_balance(BOT, 10_000.0, 700152905)

    s = bot_state.read_bot(BOT)
    assert s["starting_balance"] == 10_000.0
    assert s["starting_balance_account"] == 700152905


def test_an_anchor_from_before_this_field_existed_is_adopted_not_reset(isolated):
    """A real measurement is never discarded to satisfy a bookkeeping field."""
    bot_state.write_bot(BOT, {"starting_balance": 2_000.0})  # no account key: pre-migration

    bot_state.ensure_starting_balance(BOT, 9_996.99, 700107749)

    s = bot_state.read_bot(BOT)
    assert s["starting_balance"] == 2_000.0, "the measured anchor must survive the migration"
    assert s["starting_balance_account"] == 700107749


def test_a_caller_that_cannot_name_its_account_can_never_reset_the_anchor(isolated):
    """`None` is 'I don't know', which is not 'this is a different account'."""
    bot_state.ensure_starting_balance(BOT, 2_000.0, 700107749)

    bot_state.ensure_starting_balance(BOT, 10_000.0, None)

    assert bot_state.read_bot(BOT)["starting_balance"] == 2_000.0


# ── A RENAME arrives here looking exactly like a brand-new bot (2026-09-05) ──────────────────
#
# 🔴 The 2026-09-03 de-brand made a fresh state entry with no anchor, so the next heartbeat
# anchored it at the balance the account had already GROWN to. MEASURED 2026-09-05: the retired
# entry held 9996.99 for account 700152905 while the live one held 14538.88, so every reader of
# `total_pnl_pct` said 0.0% on an account up 45.4%. Nothing errored and no test went red.


def _seed_retired(dirpath, key, *, balance, account):
    """Write a RETIRED entry straight into the instance file — a key nothing writes any more."""
    state = bot_state._load_instance_state(dirpath)
    state[key] = {"starting_balance": balance, "starting_balance_account": account}
    bot_state._save_instance_state(dirpath, state)


def test_a_fresh_anchor_over_a_RETIRED_one_on_the_same_account_is_flagged(isolated):
    """MUTATION: return `{}` from `suspect_anchors`. RUN — red.

    This is the rename, exactly as it happened. The bot anchors at today's balance because that
    is all it can honestly measure, and the disagreement is RECORDED so a person can see that a
    number for this account already existed."""
    _seed_retired(isolated, "mpc_sos_fade_demo", balance=9_996.99, account=700152905)

    bot_state.ensure_starting_balance(BOT, 14_538.88, 700152905)

    s = bot_state.read_bot(BOT)
    assert s["starting_balance"] == 14_538.88
    assert s["starting_balance_suspect"] == {"mpc_sos_fade_demo": 9_996.99}


def test_it_REPORTS_and_never_ADOPTS(isolated):
    """MUTATION: adopt the other anchor instead of recording it. RUN — red.

    🔴 The reason this may not auto-adopt is that a rename and an ordinary second bot joining a
    grown account are the SAME SIGNATURE. The extreme leg joined this account on 2026-09-04 and
    its 14538.88 is CORRECT — adopting 9996.99 there would credit a bot that has never traded
    with 45% of somebody else's growth. Two causes, one signature; guessing fabricates a number."""
    _seed_retired(isolated, "mpc_sos_fade_demo", balance=9_996.99, account=700152905)

    bot_state.ensure_starting_balance(BOT, 14_538.88, 700152905)

    assert bot_state.read_bot(BOT)["starting_balance"] == 14_538.88


def test_an_anchor_for_a_DIFFERENT_account_is_not_flagged(isolated):
    """MUTATION: drop the account test from the scan. RUN — red. Another account's opening says
    nothing about this one, and a field that fires on unrelated bots is one readers learn to
    ignore — which is worth less than no field at all."""
    _seed_retired(isolated, "other_bot", balance=2_000.0, account=700107749)

    bot_state.ensure_starting_balance(BOT, 14_538.88, 700152905)

    assert "starting_balance_suspect" not in bot_state.read_bot(BOT)


def test_an_anchor_that_AGREES_is_not_suspect(isolated):
    """MUTATION: flag any other anchor regardless of value. RUN — red. Two bots that arrived at
    the same balance are the ordinary case, and flagging it fires on every second bot ever added
    to an account."""
    _seed_retired(isolated, "sibling", balance=14_538.88, account=700152905)

    bot_state.ensure_starting_balance(BOT, 14_538.88, 700152905)

    assert "starting_balance_suspect" not in bot_state.read_bot(BOT)


def test_a_bot_that_already_has_an_anchor_is_not_re_examined(isolated):
    """MUTATION: run the scan on every call rather than only on a fresh anchor. RUN — red.

    ⚠ The flag answers *"was this anchor written over an existing measurement"*, which is a fact
    about the MOMENT it was written. Re-deciding it every poll would raise it the first time any
    neighbour anchors differently — an event that says nothing about this bot's own number."""
    bot_state.ensure_starting_balance(BOT, 9_996.99, 700152905)
    _seed_retired(isolated, "newcomer", balance=14_538.88, account=700152905)

    bot_state.ensure_starting_balance(BOT, 14_538.88, 700152905)

    s = bot_state.read_bot(BOT)
    assert s["starting_balance"] == 9_996.99
    assert "starting_balance_suspect" not in s
