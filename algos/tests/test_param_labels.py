"""The Command Center's label for a setting, as a health message says it (2026-09-30).

A message that names `exec_risk_pct` is a message written for a compiler. These pin that the label
comes from the strategy's own meta.json, that a promoted bot's snapshot (which copies only `.py`
files) still finds it, that nothing ever raises, and that the Command Center's mirror agrees.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_ALGOS = Path(__file__).resolve().parents[1]
_REPO = _ALGOS.parent
sys.path.insert(0, str(_ALGOS / "shared"))

import param_labels as pl  # noqa: E402


def test_a_known_field_reads_as_the_CONFIGURE_TABS_label():
    """MUTATION: return `humanise(name)` unconditionally -> red."""
    assert pl.label_for("exec_risk_pct", "sos_fade") == "Risk % per trade"


def test_an_indented_label_loses_its_arrow():
    """extreme_leg's label is `   ↳ Risk % per trade` — the arrow is UI nesting, not a word."""
    assert pl.label_for("exec_risk_pct", "extreme_leg") == "Risk % per trade"


def test_an_unknown_field_or_package_falls_back_and_never_shows_the_code_name():
    assert pl.label_for("exec_sl_deep_thing", "no_such_package") == "Sl deep thing"
    assert pl.label_for("account_risk_cap_pct") == "Account risk cap %"
    assert pl.label_for("margin_safety_pct", None) == "Margin safety %"


def test_a_change_reads_label_old_arrow_new_without_float_noise():
    assert pl.change_text("exec_risk_pct", 5.0, 4.0, "sos_fade") == "Risk % per trade 5 → 4"
    assert pl.value_text(True) == "on" and pl.value_text(None) == "none"


def test_a_SNAPSHOT_finds_the_meta_json_in_the_checkout_it_sits_in(tmp_path):
    """A promote copies only `.py`, so the frozen code has no meta.json beside it. The walk up must
    pass the snapshot root (which holds `strategies/python/<pkg>/` with no meta) and reach the repo.

    MUTATION: stop the walk at the first `strategies/python/<pkg>` folder -> red."""
    repo = tmp_path / "repo"
    meta = repo / "strategies" / "python" / "demo_pkg" / "demo_pkg.meta.json"
    meta.parent.mkdir(parents=True)
    meta.write_text(json.dumps({"params": [{"name": "exec_x", "label": "The X"}]}))
    snap = repo / "algos" / "markets" / "fx" / "instances" / "b" / "deployed"
    (snap / "strategies" / "python" / "demo_pkg").mkdir(parents=True)  # .py only, no meta
    here = snap / "algos" / "shared" / "param_labels.py"
    here.parent.mkdir(parents=True)
    here.write_text("")
    assert pl._meta_path("demo_pkg", start=here) == meta


def test_an_unreadable_meta_json_falls_back_rather_than_raising(tmp_path, monkeypatch):
    bad = tmp_path / "bad.meta.json"
    bad.write_text("{not json")
    monkeypatch.setattr(pl, "_meta_path", lambda package, start=None: bad)
    pl._labels.cache_clear()
    try:
        assert pl.label_for("exec_risk_pct", "broken_pkg") == "Risk %"
    finally:
        pl._labels.cache_clear()


def test_the_COMMAND_CENTER_mirror_gives_the_same_answers():
    """Two copies of one rule drift unless compared — the same reason `alert_format` is pinned."""
    path = _REPO / "command-center" / "backend" / "services" / "param_labels.py"
    spec = importlib.util.spec_from_file_location("cc_param_labels", path)
    cc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cc)
    for name, pkg in [
        ("exec_risk_pct", "sos_fade"),
        ("exec_risk_pct", "extreme_leg"),
        ("account_risk_cap_pct", None),
        ("exec_some_new_thing", "sos_fade"),
    ]:
        assert cc.label_for(name, pkg) == pl.label_for(name, pkg), name
    assert cc.change_text("exec_risk_pct", 5.0, 4.0, "sos_fade") == pl.change_text(
        "exec_risk_pct", 5.0, 4.0, "sos_fade"
    )
