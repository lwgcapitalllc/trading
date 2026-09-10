"""scripts/check_engine_gates.py — which gate it runs on which golden export.

It runs every engine's AND every strategy's parity gate on a committed export (step 15). Two
things here fail quietly if they break: a strategy folder dropping out of discovery (the step
stays green, just smaller), and a folder holding SEVERAL compare_*.py — sos_fade does — having
its gate picked alphabetically, which runs the right tool by luck until a rename.

Mutations, each watched RED: take the first gate when two are unnamed; ignore the manifest's
`gate`; accept a named gate that does not exist; drop strategies from the discovery roots.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _runner():
    spec = importlib.util.spec_from_file_location(
        "check_engine_gates_under_test", REPO / "scripts" / "check_engine_gates.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _component(tmp_path, *gates):
    tools = tmp_path / "thing" / "tools"
    tools.mkdir(parents=True)
    for g in gates:
        (tools / g).write_text("", encoding="utf-8")
    return tmp_path / "thing"


def test_two_gates_and_no_name_is_refused_not_resolved_alphabetically(tmp_path, capsys):
    comp = _component(tmp_path, "compare_a.py", "compare_b.py")
    assert _runner()._gate_for(comp, {}) is None
    assert "golden.json names none" in capsys.readouterr().out


def test_the_named_gate_is_the_one_run(tmp_path):
    comp = _component(tmp_path, "compare_a.py", "compare_b.py")
    assert (
        _runner()._gate_for(comp, {"gate": "tools/compare_b.py"}) == comp / "tools" / "compare_b.py"
    )


def test_a_named_gate_that_does_not_exist_is_refused(tmp_path, capsys):
    comp = _component(tmp_path, "compare_a.py")
    assert _runner()._gate_for(comp, {"gate": "tools/compare_gone.py"}) is None
    assert "does not exist" in capsys.readouterr().out


def test_a_lone_gate_needs_no_name(tmp_path):
    comp = _component(tmp_path, "compare_a.py")
    assert _runner()._gate_for(comp, {}) == comp / "tools" / "compare_a.py"


def test_sos_fade_names_its_parity_gate_and_would_be_refused_without_it():
    """The real folder: two tools, so the name is what picks the parity gate."""
    run = _runner()
    comp = REPO / "strategies" / "python" / "sos_fade"
    manifest = json.loads((comp / "exports" / "golden" / "golden.json").read_text())
    assert len(list(comp.glob("tools/compare_*.py"))) >= 2  # premise
    assert run._gate_for(comp, manifest) == comp / "tools" / "compare_strategy.py"
    assert run._gate_for(comp, {}) is None


def test_every_strategy_golden_is_discovered_at_its_measured_warmup():
    found = {
        (c.name, csv.name): (gate.name if gate else None, warmup)
        for c, gate, csv, warmup, _x in _runner()._discover()
    }
    assert found[("sos_fade", "VANTAGE_XAUUSD_M15_20220bars.csv")] == ("compare_strategy.py", 468)
    assert found[("extreme_leg", "VANTAGE_XAUUSD_M5_20288bars.csv")] == (
        "compare_extreme_leg.py",
        0,
    )
    assert found[("b_leg", "VANTAGE_XAUUSD_M15_20220bars.csv")] == ("compare_bleg.py", 468)
    assert found[("bos", "VANTAGE_XAUUSD_M15_20220bars.csv")] == ("compare_bos.py", 0)
