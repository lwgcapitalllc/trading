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
    assert _scan("loss_recovery")["display_under"] == "mpc_sos_fade"


def test_a_strategy_that_declares_nothing_is_top_level():
    """`None`, never `""`. An empty string is truthy nowhere useful and falsy everywhere it
    matters, so it would read as a declared parent in some checks and no parent in others."""
    assert _scan("mpc_sos_fade")["display_under"] is None


def test_every_declared_parent_IS_a_real_strategy():
    """🔴 The durable one. A typo'd id renders the row at the top level in silence — the page
    cannot tell "no parent" from "a parent nobody has heard of", so nothing on screen is wrong
    and the nesting has simply gone missing."""
    rows = [_scan(p.name) for p in sorted(_PY.iterdir()) if (p / "__init__.py").exists()]
    ids = {r["id"] for r in rows}
    assert "mpc_sos_fade" in ids, "the scan found no strategies — this test would pass vacuously"
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
    assert rec["display_under"] == "mpc_sos_fade"
    for field in ("id", "name", "class_name", "runner", "category", "param_schema"):
        assert rec.get(field), f"nesting must not blank {field}"
    assert rec["runner"] == "python"


def test_the_B_LEG_IS_NOT_NESTED_YET_and_this_is_the_reminder_why():
    """🔴 Aaron asked for B-LEG to nest here too and it is NOT SHIPPED. Rule 22: a changed
    strategy package may not be committed until its `compare_bleg.py` gate has run and PASSED on
    a real export, and on the only B-LEG export on disk
    (`engines/VANTAGE_XAUUSD, 15_9f68f.csv`) it is RED — byte-identically red at HEAD, so the
    nesting did not cause it, and a pre-existing red is still a red.

    ⚠ This test is a TRIPWIRE, not an opinion. When the declaration is added it goes red, which
    is the prompt to re-run the gate on a fresh export in the same change. Delete it then.
    """
    assert _scan("mpc_bleg")["display_under"] is None
