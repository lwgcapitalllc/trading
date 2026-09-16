"""Every runnable self-sizing strategy marks its risk-per-trade setting, so the run form can lift it.

Aaron, 2026-09-16: the risk % must be overridable at the top of the run form on EVERY strategy. A
self-sizing strategy owns that value as an ordinary setting, and the form finds it through the
`role: "risk_pct"` mark in the package's meta.json. A package that forgets the mark still runs —
the form just shows a warning — so nothing else would go red.

Scans the REAL packages, so a new strategy added without the mark fails here.

⚠ Mutation-proven: deleting the `"role"` line from realign.meta.json turns
`test_every_self_sizing_strategy_marks_one_risk_setting` red, and dropping `"role"` from the
scanner's meta whitelist turns both red.
"""

from __future__ import annotations

import sys

import config as cfg
import pytest
from services import strategy_scanner


@pytest.fixture
def scanned_rows():
    before = dict(sys.modules)
    for name in [n for n in sys.modules if n == "strategies" or n.startswith("strategies.")]:
        del sys.modules[name]
    root = cfg.MONOREPO_ROOT
    rows = []
    for pkg in sorted((root / "strategies" / "python").iterdir()):
        if not (pkg / "__init__.py").exists():
            continue
        row, _err = strategy_scanner._parse_python_package(pkg, root)
        if row is not None:
            rows.append(row)
    yield rows
    for name in [n for n in sys.modules if n not in before]:
        del sys.modules[name]
    sys.modules.update(before)


def _runnable_self_sizing(rows):
    return [r for r in rows if r["self_sizing"] and not r["requires_source"]]


def test_scan_found_the_self_sizing_strategies(scanned_rows):
    """Guards the test itself: an empty scan would pass the check below vacuously."""
    ids = {r["id"] for r in _runnable_self_sizing(scanned_rows)}
    assert {"sos_fade", "bos", "extreme_leg", "b_leg", "realign"} <= ids


def test_every_self_sizing_strategy_marks_one_risk_setting(scanned_rows):
    for row in _runnable_self_sizing(scanned_rows):
        marked = [p for p in row["param_schema"] if p.get("role") == "risk_pct"]
        assert len(marked) == 1, (
            f"{row['id']}: expected exactly one setting marked role=risk_pct in its meta.json, "
            f"found {[p['name'] for p in marked]}"
        )
        # The mark must sit on a real, numeric config field — a meta entry for a name the
        # config does not have is dropped by the scanner and would never reach here.
        assert marked[0]["type"] in ("double", "int"), (row["id"], marked[0])
