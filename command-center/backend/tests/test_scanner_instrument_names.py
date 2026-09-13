"""A python strategy's instrument facts have NAMES, and a scanner change reaches a row (2026-09-13).

`strategy_scanner` files six config fields as instrument facts (`_PY_FOUNDATIONAL`) — the tick
size, point value, trading-day rollover, fill model, account profile and symbol. It gave them no
name but the field's own, so the finished-run panel's "Instrument & broker" fold read `mintick`
and `daily close hour ny` on every python strategy (sos_fade's meta named three of the six).

The second half is what makes the first reach a page: a python row was re-written only when the
package's FILES or its meta moved, so a change to the SCANNER never reached a strategy whose
source was untouched — b_leg, bos and realign would have kept the raw names for ever.

⚠ A fail-watch against HEAD is VACUOUS (the names table and the comparison did not exist), so
non-vacuity is by MUTATION — each test names the one that turns it red.
"""

from __future__ import annotations

import dataclasses
import sys
import textwrap
from pathlib import Path

import pytest
from services import strategy_scanner


@dataclasses.dataclass
class _Cfg:
    risk_pct: float = 1.0  # a strategy's own setting — named by its meta, never here
    mintick: float = 0.01
    point_value: float = 1.0
    daily_close_hour_ny: int = 17
    fill_model: str = "bar"
    account_profile: str = "vantage_demo"
    symbol: str = "XAUUSD"


def test_every_instrument_fact_the_scanner_files_has_a_name():
    """MUTATION: `param.update(_PY_FOUNDATIONAL_WORDS.get(f.name, {}))` -> `param.update({})`
    turns this red."""
    assert set(strategy_scanner._PY_FOUNDATIONAL_WORDS) == set(strategy_scanner._PY_FOUNDATIONAL)
    by = {p["name"]: p for p in strategy_scanner._py_param_schema(_Cfg)}
    for name in strategy_scanner._PY_FOUNDATIONAL:
        assert by[name]["category"] == "foundational"
        assert by[name].get("label"), f"{name} has no name but its field's"
    assert by["mintick"]["label"] == "Tick size"
    assert by["daily_close_hour_ny"]["unit"]  # the hour's unit rides with the value
    assert "label" not in by["risk_pct"]  # a strategy's own setting is its meta's to name


def _write_pkg(root: Path, name: str) -> Path:
    pkg = root / "strategies" / "python" / name
    pkg.mkdir(parents=True, exist_ok=True)
    (root / "strategies" / "__init__.py").touch()
    (root / "strategies" / "python" / "__init__.py").touch()
    (pkg / "__init__.py").write_text(
        textwrap.dedent(f"""
        from dataclasses import dataclass

        @dataclass
        class Cfg:
            risk_pct: float = 1.0
            mintick: float = 0.01

        class Strat:
            pass

        LAB_STRATEGY = {{"name": "{name}", "config": Cfg, "strategy": Strat}}
    """)
    )
    return pkg


@pytest.fixture
def _clean_modules():
    """Same isolation as test_strategy_import_freshness.py, for the same reason: another test
    imports the real `strategies` package first and pins its `__path__` to the monorepo."""
    before = dict(sys.modules)
    for name in [n for n in sys.modules if n == "strategies" or n.startswith("strategies.")]:
        del sys.modules[name]
    path_before = list(sys.path)
    yield
    for name in [n for n in sys.modules if n not in before]:
        del sys.modules[name]
    sys.modules.update(before)
    sys.path[:] = path_before


def _mintick_label(lab_db, strategy_id: str) -> str:
    row = lab_db.get_strategy(strategy_id)
    return next(p for p in row["param_schema"] if p["name"] == "mintick").get("label")


def test_a_scan_rewrites_a_row_whose_schema_the_scanner_now_builds_differently(
    tmp_path, monkeypatch, fresh_db, _clean_modules
):
    """MUTATION: `and _same_schema(existing, data)` -> `and True` in the python scan loop turns
    this red — the third scan skips a row whose files never moved."""
    import config as cfg
    from services import lab_db

    _write_pkg(tmp_path, "probe_names")
    monkeypatch.setattr(cfg, "MONOREPO_ROOT", tmp_path)

    first = strategy_scanner.scan_strategies()
    assert first["added"] == 1
    assert _mintick_label(lab_db, "probe_names") == "Tick size"

    # Nothing moved: the row is skipped, so the comparison does not make every scan a write.
    again = strategy_scanner.scan_strategies()
    assert (again["updated"], again["skipped"]) == (0, 1)

    # The SCANNER learns a new name; nothing in the package changed.
    monkeypatch.setitem(strategy_scanner._PY_FOUNDATIONAL_WORDS, "mintick", {"label": "Price step"})
    third = strategy_scanner.scan_strategies()
    assert third["updated"] == 1
    assert _mintick_label(lab_db, "probe_names") == "Price step"
