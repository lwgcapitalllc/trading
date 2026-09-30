"""The chart's pip size — which instruments get one, and that EVERY served spec carries it.

🔴 The serve-path tests are the ones that matter. A warm cache is streamed as raw bytes and never
parsed, so a field added only at BUILD time would reach no run built before it — every existing
chart would quietly show no pips. Proven by MUTATION 2026-09-26: making the serve path hand back
the raw cached bytes (the old behaviour) turns all three splice tests red.
"""

import json

import pytest
from services import chart_spec
from services.pip_size import pip_size


@pytest.mark.parametrize(
    "sym, want",
    [
        ("XAUUSD", 0.10),  # PU Prime's gold convention — $0.10 a pip
        ("XAUUSD.p", 0.10),  # the broker suffix is not part of the symbol
        ("EURUSD", 0.0001),
        ("AUDJPY.s", 0.01),  # JPY quote → two-decimal pip
        ("GBPJPY", 0.01),
        ("XAGUSD", None),  # silver has no settled convention — unknown, not guessed
        ("US30", None),
        ("MES", None),  # futures quote ticks, not pips
        ("NVIDIA", None),  # six letters, not a currency pair
        ("", None),
    ],
)
def test_pip_size(sym, want):
    assert pip_size(sym) == want


@pytest.fixture
def lab_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_spec, "LAB_RESULTS_DIR", tmp_path)
    return tmp_path


def _cache(lab_dir, run_id, text, instrument, monkeypatch):
    d = lab_dir / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "chart_spec.json").write_text(text)
    monkeypatch.setattr(
        chart_spec.lab_db,
        "get_run",
        lambda rid: {"instrument": instrument} if rid == run_id else None,
    )


def test_a_warm_cache_built_before_the_field_is_served_with_it(lab_dir, monkeypatch):
    _cache(lab_dir, "r1", '{"instrument":"XAUUSD.p","trades":[]}\n', "XAUUSD.p", monkeypatch)
    got = json.loads(chart_spec.served_chart_spec_bytes("r1"))
    assert got == {"instrument": "XAUUSD.p", "trades": [], "pipSize": 0.1}


def test_an_unknown_convention_is_served_as_null_not_zero(lab_dir, monkeypatch):
    _cache(lab_dir, "r2", '{"instrument":"US30"}', "US30", monkeypatch)
    assert json.loads(chart_spec.served_chart_spec_bytes("r2"))["pipSize"] is None


def test_an_empty_object_still_splices_to_valid_json(lab_dir, monkeypatch):
    _cache(lab_dir, "r3", "{}", "EURUSD", monkeypatch)
    assert json.loads(chart_spec.served_chart_spec_bytes("r3")) == {"pipSize": 0.0001}


def test_no_cache_is_still_no_cache(lab_dir):
    assert chart_spec.served_chart_spec_bytes("never-built") is None
