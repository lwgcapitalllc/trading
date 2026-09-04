"""The Strategies page's TREE — a strategy may declare which row it is listed under.

Display grouping only: `LAB_STRATEGY["display_under"]` names another strategy's id, the page
lists the declarer beneath it, and nothing else changes. It restricts no run, no stack and no
optimization.

🔴 EVERY FAILURE HERE IS SILENT. A typo'd parent id does not error — the row simply renders at the
top level, which is exactly what a strategy with no parent looks like. A dropped field does the
same. So these check the declaration RESOLVES, not that the page draws it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as cfg  # noqa: E402
from services import strategy_scanner  # noqa: E402

_PY = Path(cfg.MONOREPO_ROOT) / "strategies" / "python"


def _scan(pkg: str) -> dict:
    row, err = strategy_scanner._parse_python_package(_PY / pkg, Path(cfg.MONOREPO_ROOT))
    assert err is None, err
    assert row is not None
    return row


def test_the_recovery_rule_is_listed_under_the_bot_it_recovers():
    assert _scan("loss_recovery")["display_under"] == "sos_fade"


def test_a_strategy_that_declares_nothing_is_top_level():
    """`None`, never `""`. An empty string is truthy nowhere useful and falsy everywhere it
    matters, so it would read as a declared parent in some checks and no parent in others."""
    assert _scan("sos_fade")["display_under"] is None


def test_every_declared_parent_IS_a_real_strategy():
    """🔴 The durable one. A typo'd id renders the row at the top level in silence — the page
    cannot tell "no parent" from "a parent nobody has heard of", so nothing on screen is wrong
    and the nesting has simply gone missing."""
    rows = [_scan(p.name) for p in sorted(_PY.iterdir()) if (p / "__init__.py").exists()]
    ids = {r["id"] for r in rows}
    assert "sos_fade" in ids, "the scan found no strategies — this test would pass vacuously"
    for r in rows:
        under = r["display_under"]
        if under is None:
            continue
        assert under in ids, f"{r['id']} is listed under '{under}', which is not a strategy"
        assert under != r["id"], f"{r['id']} is listed under itself"


def test_nesting_takes_NOTHING_away_from_the_row():
    """Display grouping only. A nested strategy keeps every field a top-level one has, so it is
    still run, stacked, optimized and deployed identically. The two ideas are separate: nesting
    says where a row is DRAWN, `requires_source` says whether it can run alone."""
    rec = _scan("loss_recovery")
    assert rec["display_under"] == "sos_fade"
    for field in ("id", "name", "class_name", "runner", "category", "param_schema"):
        assert rec.get(field), f"nesting must not blank {field}"
    assert rec["runner"] == "python"


def test_the_B_LEG_nests_under_the_A_PLUS_bot_too():
    """The tripwire this replaces asserted the OPPOSITE — B-LEG was held back because rule 22
    forbids shipping a changed strategy package until its parity harness has run GREEN on a real
    export, and the only B-LEG export on disk at the time was red (byte-identically red at HEAD,
    so the nesting never caused it — a pre-existing red is still a red).

    Shipped 2026-08-23 on a fresh export: `compare_bleg.py` on
    `engines/VANTAGE_XAUUSD, 5_f8228.csv` — 20,573 M5 bars, identical on every bar from 0.

    Watched RED by deleting the declaration from the package: the assert below fails with None.
    """
    assert _scan("b_leg")["display_under"] == "sos_fade"


def test_nesting_the_B_LEG_leaves_it_runnable_on_its_own():
    """The whole risk of the declaration: it must move where the row is DRAWN and nothing else.
    B-LEG has setups of its own, so it must never pick up the flag that refuses a standalone run.

    Watched RED by adding `requires_source` to the B-LEG package alongside the nesting.
    """
    bleg = _scan("b_leg")
    assert not bleg.get("requires_source")
    assert bleg["runner"] == "python"


def test_the_extreme_leg_is_TOP_LEVEL_and_that_is_a_decision():
    """It was listed under the A+ bot until 2026-09-02, when Aaron moved it to root.

    🔴 The reason is worth keeping, because the original reasoning was not wrong — it was drawing
    the wrong thing. The suite IS carved up by leg off one structure stream and this IS the leg
    before the one A+ trades; but an indent reads as "child of", and this bot is a SIBLING. It has
    its own Pine source, its own parity gate, and it runs standalone, in any stack, on any
    instrument. What made the indent misread is that `loss_recovery` sits at the same level and
    genuinely cannot run without its parent — one visual level was carrying two relationships.

    ⚠ This test exists because the field's failure mode is SILENT IN BOTH DIRECTIONS. A dropped
    declaration and a typo'd parent both render at the top level, so re-adding it — or reversing
    this decision by accident — would show up nowhere on the page. Watched RED by putting
    `"display_under": "sos_fade"` back in the package.
    """
    assert _scan("extreme_leg")["display_under"] is None


def test_the_extreme_leg_still_stands_alone_after_the_move():
    """The mirror of the B-LEG check above: moving a row must change where it is DRAWN and nothing
    else. It must not pick up the flag that refuses a standalone run, and it must stay a python
    row the stack builder can tick.

    Watched RED by adding `requires_source` to the package alongside the move.
    """
    xl = _scan("extreme_leg")
    assert not xl.get("requires_source")
    assert xl["runner"] == "python"
