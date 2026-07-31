"""What a live bot is configured with, and the line between what may and may not change.

The editable/read-only split is a safety property, not a UI preference: everything in
`RUNTIME_EDITABLE` can be changed under a running bot without invalidating its backtest,
and everything else cannot. These tests pin that line from both sides.
"""

import pytest

from services import bot_params


def _config(**overrides):
    cfg = {
        "bot_key": "demo_bot",
        "display_name": "Demo Bot",
        "account": 700107749,
        "server": "PUPrime-Demo",
        "symbol": "XAUUSD.s",
        "timeframe": "M15",
        "mt5_path": r"C:\MT5_FFT\terminal64.exe",
        "magic": 770115,
        "strategy_package": "mpc_sos_fade",
        "strategy_class": "MpcSosFadeStrategy",
        "strategy_version": 0,
        "strategy_source_hash": "6f78d102bfd9c4e55a0fd327cf581a0a",
        "promoted_commit": "8fb2986",
        "promoted_at": "2026-07-31",
        "strategy_params": {
            "exec_risk_pct": 10.0,
            "exec_sl_level": "0.886",
            "aplus_window": 4320,
            "exec_longs": True,
        },
        "_exec_risk_pct": "DECISION PENDING — 10% is $200 on this account.",
        "_README": "The bot.",
    }
    cfg.update(overrides)
    return cfg


_SCHEMA = [
    {"name": "aplus_window", "label": "Arm → SOS timeout", "group": "What arms a setup",
     "type": "int", "unit": "minutes", "desc": "How long an armed setup waits."},
    {"name": "exec_risk_pct", "label": "Risk per trade", "group": "Position sizing",
     "type": "double", "unit": "%", "core": True},
]


# ── the view ────────────────────────────────────────────────────────────────────
def test_the_risk_lever_is_the_only_editable_row():
    v = bot_params.build_view("demo_bot", _config(), _SCHEMA)
    assert [r["name"] for r in v["runtime"]] == ["exec_risk_pct"]
    assert all(not r["editable"] for r in v["strategy"])


def test_every_strategy_param_is_shown_even_with_no_schema():
    """A missing label must never hide a value — the whole point of the page is that
    nothing about a running bot is invisible."""
    v = bot_params.build_view("demo_bot", _config(), param_schema=None)
    shown = {r["name"] for r in v["runtime"]} | {r["name"] for r in v["strategy"]}
    assert shown == set(_config()["strategy_params"])


def test_an_unschemad_param_falls_back_to_a_readable_name():
    v = bot_params.build_view("demo_bot", _config(), _SCHEMA)
    row = next(r for r in v["strategy"] if r["name"] == "exec_sl_level")
    assert row["label"] == "exec sl level"      # not the raw snake_case, not blank


def test_the_config_note_rides_along_with_the_field_it_explains():
    """`_exec_risk_pct` is the reason the number is what it is — written at the moment the
    decision was made, which is the only time it is accurate."""
    v = bot_params.build_view("demo_bot", _config(), _SCHEMA)
    row = next(r for r in v["runtime"] if r["name"] == "exec_risk_pct")
    assert "DECISION PENDING" in row["note"]


def test_the_version_pin_and_promoted_commit_are_surfaced():
    """Which code is this actually running? That question must be answerable here."""
    v = bot_params.build_view("demo_bot", _config(), _SCHEMA)
    assert v["version"]["strategy_source_hash"].startswith("6f78d102")
    assert v["version"]["promoted_commit"] == "8fb2986"


def test_no_secret_can_reach_the_view():
    """An instance config must never hold a credential, but if one is ever added by
    mistake it must not be the Bots page that publishes it to a browser."""
    v = bot_params.build_view("demo_bot", _config(), _SCHEMA)
    blob = repr(v).lower()
    for smell in ("password", "token", "secret", "apikey", "api_key"):
        assert smell not in blob


def test_strategy_rows_follow_the_labs_param_order():
    v = bot_params.build_view("demo_bot", _config(), _SCHEMA)
    names = [r["name"] for r in v["strategy"]]
    assert names.index("aplus_window") < names.index("exec_longs")   # schema'd first


# ── validation ──────────────────────────────────────────────────────────────────
def test_a_strategy_param_is_refused_even_if_the_frontend_asks():
    """The backend is authoritative about the editable set — a frontend bug must not be
    able to widen it, because widening it is exactly what makes the version pin theatre."""
    with pytest.raises(bot_params.RuntimeUpdateError) as e:
        bot_params.validate_runtime({"aplus_window": 100})
    assert "aplus_window" in str(e.value)


def test_a_legal_change_comes_back_as_a_float():
    assert bot_params.validate_runtime({"exec_risk_pct": "5"}) == {"exec_risk_pct": 5.0}


@pytest.mark.parametrize("bad", [0, 0.05, 35.1, 100, -5])
def test_out_of_range_risk_is_refused(bad):
    with pytest.raises(bot_params.RuntimeUpdateError):
        bot_params.validate_runtime({"exec_risk_pct": bad})


def test_out_of_range_is_rejected_not_clamped():
    """A silently clamped risk is the worst outcome available: the user believes they set
    50, the bot trades 35, and nothing on screen disagrees."""
    with pytest.raises(bot_params.RuntimeUpdateError) as e:
        bot_params.validate_runtime({"exec_risk_pct": 50})
    assert "between" in str(e.value)


@pytest.mark.parametrize("bad", ["", None, "abc", float("nan"), float("inf")])
def test_a_non_number_is_refused(bad):
    with pytest.raises(bot_params.RuntimeUpdateError):
        bot_params.validate_runtime({"exec_risk_pct": bad})


def test_an_empty_update_is_refused():
    with pytest.raises(bot_params.RuntimeUpdateError):
        bot_params.validate_runtime({})


def test_arming_is_not_editable_from_here():
    """Dry run → live is reported, never written. A web button that quietly arms a bot is
    a different decision from resizing one, and `--live` stays something you type."""
    assert "live" not in bot_params.RUNTIME_EDITABLE
    assert "dry_run" not in bot_params.RUNTIME_EDITABLE
    with pytest.raises(bot_params.RuntimeUpdateError):
        bot_params.validate_runtime({"live": 1})


def test_every_editable_field_declares_bounds():
    """An editable field with no range is an unbounded text box pointed at a live account."""
    assert set(bot_params.RUNTIME_BOUNDS) == bot_params.RUNTIME_EDITABLE
