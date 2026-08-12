"""`starting_balance` is an anchor for an ACCOUNT, and it used to be stored as if it were one
for a BOT.

🔴 **Written after the anchor survived a move it had no business surviving.** On 2026-08-12
`mpc_sos_fade_demo` was moved from the PU Prime Standard demo (anchored at $2,000, grown to
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

BOT = "mpc_sos_fade_demo"


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
    bot_state.write_bot(BOT, {"starting_balance": 2_000.0})       # no account key: pre-migration

    bot_state.ensure_starting_balance(BOT, 9_996.99, 700107749)

    s = bot_state.read_bot(BOT)
    assert s["starting_balance"] == 2_000.0, "the measured anchor must survive the migration"
    assert s["starting_balance_account"] == 700107749


def test_a_caller_that_cannot_name_its_account_can_never_reset_the_anchor(isolated):
    """`None` is 'I don't know', which is not 'this is a different account'."""
    bot_state.ensure_starting_balance(BOT, 2_000.0, 700107749)

    bot_state.ensure_starting_balance(BOT, 10_000.0, None)

    assert bot_state.read_bot(BOT)["starting_balance"] == 2_000.0
