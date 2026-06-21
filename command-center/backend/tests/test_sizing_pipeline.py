"""
Sizing pipeline tests (services/sizing_pipeline) — the runner-export → engine → files wiring.

Feeds synthetic per-trade records (the runner→engine contract) through the pipeline and
checks the engine result plus the persisted artifacts (decisions.jsonl, timeline, daily_pnl).
"""

import json

from services.sizing_pipeline import (
    run_sizing_engine, is_micro_instrument, engine_result_to_kpis, size_run_for_rulesets,
)
from services.sizing_engine import MODE_CONSISTENT, MODE_BULLET, EngineResult, SizedTrade


def _ruleset():
    return {
        "id": "lucidflex_50k_eval", "ruleset_type": "prop_eval", "account_size": 50000,
        "profit_target": 3000, "max_loss_eod": 2000, "mll_lock_balance": 50100,
        "consistency_pct": None, "daily_loss_cap": None, "risk_per_trade_pct": None,
        "daily_halt_fraction": None, "daily_profit_target": None,
        "max_drawdown_from_peak_pct": None,
        "max_contracts": {"mini_max": 4, "micro_max": 40, "scaling": None},
    }


def _records():
    return [
        {"index": 1, "entry_time": "2024-01-02T09:40:00", "exit_time": "2024-01-02T10:00:00",
         "direction": "Long", "entry_price": 17000, "exit_price": 17010, "stop_distance": 5,
         "point_value": 2, "commission_per_side": 0, "exit_reason": "ORB_Long Profit target"},
        {"index": 2, "entry_time": "2024-01-03T09:40:00", "exit_time": "2024-01-03T09:55:00",
         "direction": "Short", "entry_price": 17000, "exit_price": 17005, "stop_distance": 5,
         "point_value": 2, "commission_per_side": 0, "exit_reason": "Stop loss"},
    ]


def test_micro_inference():
    assert is_micro_instrument("MNQ 06-26") is True
    assert is_micro_instrument("NQ 06-26") is False
    assert is_micro_instrument("") is False


def test_pipeline_runs_engine_and_persists(tmp_path):
    res = run_sizing_engine("run42", _records(), _ruleset(), mode=MODE_CONSISTENT,
                            instrument="MNQ 06-26", strategy="ORB", results_dir=tmp_path)

    # Engine produced one sized day per trade (intraday, one trade each day).
    assert [d["date"] for d in res.daily_pnl] == ["2024-01-02", "2024-01-03"]
    assert len(res.decisions) == 2

    run_dir = tmp_path / "run42"
    assert (run_dir / "decisions.jsonl").exists()
    assert (run_dir / "engine_timeline.json").exists()
    assert (run_dir / "engine_daily_pnl.json").exists()

    # decisions.jsonl is one JSON object per line, and round-trips.
    lines = (run_dir / "decisions.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["strategy"] == "ORB" and first["instrument"] == "MNQ 06-26"
    assert first["exit"]["reason"] == "target"          # classified from "Profit target"

    daily = json.loads((run_dir / "engine_daily_pnl.json").read_text())
    assert daily == res.daily_pnl


def test_pipeline_bullet_sizes_to_ladder(tmp_path):
    # Bullet on a micro instrument → capped by the firm's micro ladder (40).
    res = run_sizing_engine("run43", _records()[:1], _ruleset(), mode=MODE_BULLET,
                            instrument="MNQ 06-26", results_dir=tmp_path)
    assert res.decisions[0]["sizing"]["contracts"] == 40
    assert res.decisions[0]["sizing"]["bound_by"] == "contract_ladder"


def test_size_run_for_rulesets_sizes_each_and_persists_primary_only(tmp_path):
    # Two firms with different micro ladders → bullet sizes each to its own cap.
    firm_a = {**_ruleset(), "id": "firm_a"}
    firm_a["max_contracts"] = {"mini_max": 4, "micro_max": 40, "scaling": None}
    firm_b = {**_ruleset(), "id": "firm_b"}
    firm_b["max_contracts"] = {"mini_max": 2, "micro_max": 10, "scaling": None}

    out = size_run_for_rulesets("run50", _records()[:1], [firm_a, firm_b],
                                mode=MODE_BULLET, instrument="MNQ 06-26",
                                results_dir=tmp_path)

    # One grade-ready entry per ruleset, each with its own sized contracts.
    assert set(out) == {"firm_a", "firm_b"}
    assert out["firm_a"]["result"].decisions[0]["sizing"]["contracts"] == 40
    assert out["firm_b"]["result"].decisions[0]["sizing"]["contracts"] == 10
    assert "net_pnl" in out["firm_a"]["kpis"] and "net_pnl" in out["firm_b"]["kpis"]

    # Only the PRIMARY (first) ruleset's timeline is persisted — one sized timeline per run.
    assert (tmp_path / "run50" / "engine_timeline.json").exists()
    assert (tmp_path / "run50" / "engine_daily_pnl.json").exists()


def _sized(index, contracts, net, skipped=False):
    return SizedTrade(index=index, day="2024-01-02", direction=1, contracts=contracts,
                      net_pnl=net, bound_by="x", risk_per_contract=10.0, skipped=skipped)


def test_kpis_from_engine_result_derives_summary():
    # Two wins (+300, +100), one loss (-200), one skipped (must not count).
    res = EngineResult(ruleset_id="r", net_pnl=200.0, sized_trades=[
        _sized(1, 2, 300.0), _sized(2, 1, -200.0), _sized(3, 1, 100.0),
        _sized(4, 0, 0.0, skipped=True),
    ])
    k = engine_result_to_kpis(res)
    assert k["trade_count"] == 3                 # skipped excluded
    assert k["net_pnl"] == 200.0
    assert k["profit_factor"] == 2.0             # 400 gross win / 200 gross loss
    assert k["win_rate"] == 66.7                 # 2 of 3
    assert k["avg_win"] == 200.0 and k["avg_loss"] == -200.0


def test_kpis_max_drawdown_is_peak_to_trough():
    # Equity walk by index: +500 (peak 500) → -300 (trough 200) → +100 (300). Max DD = 300.
    res = EngineResult(ruleset_id="r", net_pnl=300.0, sized_trades=[
        _sized(1, 1, 500.0), _sized(2, 1, -300.0), _sized(3, 1, 100.0),
    ])
    assert engine_result_to_kpis(res)["max_drawdown"] == 300.0


def test_kpis_no_losses_profit_factor_is_finite():
    res = EngineResult(ruleset_id="r", net_pnl=150.0, sized_trades=[
        _sized(1, 1, 150.0),
    ])
    k = engine_result_to_kpis(res)
    assert k["profit_factor"] == 150.0           # finite stand-in, not inf
    assert "avg_loss" not in k
