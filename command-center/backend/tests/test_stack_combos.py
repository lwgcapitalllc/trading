"""Any mix of a shared stack's legs is REPLAYED on its own account — never sliced from the full book.

The page used to refuse every mix short of all-on or one-on, because the only books stored were the
full shared one and each leg's solo control, and slicing the full book puts dollars on a leg that
were sized off a balance the removed legs grew. `services/stack_combos` fills the gap by replaying
the mix. These tests pin the seams that would make it lie: which legs reach the replay, a book kept
beside a stack that has since been re-persisted, and a dependent leg run without its parent.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from services import gradable, lab_db, portfolio_runner, stack_combos

LEGS = ["extreme_leg", "realign", "sos_fade"]


@pytest.fixture
def stack(tmp_path, monkeypatch):
    """A finished three-leg shared stack, with its full book's summary on disk."""
    monkeypatch.setattr(portfolio_runner, "_LAB_RESULTS_DIR", tmp_path)
    rows = [
        {"strategy_id": s, "status": "complete", "stack_source": None, "run_id": f"r_{s}"}
        for s in LEGS
    ]
    monkeypatch.setattr(
        lab_db, "get_stack_settings", lambda sid: {"mode": "shared", "account_size": 10_000}
    )
    monkeypatch.setattr(lab_db, "list_stack_runs", lambda sid: rows)
    sdir = tmp_path / "st_x"
    sdir.mkdir()
    (sdir / "shared_summary.json").write_text(json.dumps({"written_at": 111}))
    return SimpleNamespace(dir=sdir, rows=rows)


def _fake_run(names):
    trade = SimpleNamespace(r=2.0)
    return SimpleNamespace(
        cancelled=False,
        per_leg={n: [trade] for n in names},
        opening_balance=10_000.0,
        closing_balance=10_400.0,
        contention=[],
    )


def _stub_replay(monkeypatch, seen):
    monkeypatch.setattr(
        gradable,
        "rebuild_legs",
        lambda sid: [{"strategy_id": s, "class_name": "X", "params": {}} for s in LEGS],
    )

    def fake_build_and_run(
        legs, settings, *, on_progress=None, should_cancel=None, solo_control=True
    ):
        seen["legs"] = [leg["strategy_id"] for leg in legs]
        seen["solo_control"] = solo_control
        names = seen["legs"]
        specs = [SimpleNamespace(name=n, config=SimpleNamespace(point_value=100.0)) for n in names]
        return _fake_run(names), specs

    monkeypatch.setattr(portfolio_runner, "_build_and_run", fake_build_and_run)
    import backtest.output as out

    monkeypatch.setattr(
        out,
        "build_results",
        lambda trades, **k: {
            "equity_curve": [{"r": t.r, "direction": "Long"} for t in trades],
            "daily_pnl": [],
        },
    )


def test_a_mix_replays_ONLY_its_own_legs_and_is_then_served(stack, monkeypatch):
    """🔴 The replay must be handed exactly the legs that are switched on. Handing it all three
    would store the full book under a two-leg name — the same numbers the page refused to compose,
    now wearing a label that says they were replayed."""
    seen: dict = {}
    _stub_replay(monkeypatch, seen)
    assert stack_combos.read_combo("st_x", ["sos_fade", "realign"]) is None

    stack_combos._replay("st_x", ["sos_fade", "realign"])

    assert seen["legs"] == ["realign", "sos_fade"]
    assert seen["solo_control"] is False  # each leg's solo book is already on the stack
    book = stack_combos.read_combo("st_x", ["realign", "sos_fade"])
    assert book is not None and set(book["legs"]) == {"realign", "sos_fade"}
    assert book["summary"]["legs"]["sos_fade"]["r"] == 2.0


def test_a_mix_kept_beside_an_OLDER_full_book_reads_as_not_stored(stack, monkeypatch):
    """A stack whose full book is re-written (a backfill with --force) must not keep serving mixes
    replayed against its previous self — the two would describe different runs side by side."""
    seen: dict = {}
    _stub_replay(monkeypatch, seen)
    stack_combos._replay("st_x", ["realign", "sos_fade"])
    assert stack_combos.read_combo("st_x", ["realign", "sos_fade"]) is not None

    (stack.dir / "shared_summary.json").write_text(json.dumps({"written_at": 222}))
    assert stack_combos.read_combo("st_x", ["realign", "sos_fade"]) is None


def test_a_dependent_leg_is_REFUSED_without_its_parent(stack):
    """A leg that arms off another leg's trades would arm off nothing and return an empty book —
    indistinguishable from a rule that found no setups."""
    stack.rows[0]["stack_source"] = "sos_fade"
    why = stack_combos.refusal("st_x", ["extreme_leg", "realign"])
    assert why and "sos_fade" in why
    assert stack_combos.refusal("st_x", ["extreme_leg", "sos_fade"]) is None


def test_every_pair_of_a_three_leg_stack_is_missing_until_replayed(stack):
    assert stack_combos.missing("st_x") == [
        ["extreme_leg", "realign"],
        ["extreme_leg", "sos_fade"],
        ["realign", "sos_fade"],
    ]


def test_a_screen_has_no_mixes_to_replay(stack, monkeypatch):
    """On a screen every leg already traded its own full account, so any subset is honest as it is."""
    monkeypatch.setattr(lab_db, "get_stack_settings", lambda sid: {"mode": "screen"})
    assert stack_combos.refusal("st_x", ["realign", "sos_fade"])
