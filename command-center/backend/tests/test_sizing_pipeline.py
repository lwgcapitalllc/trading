"""
Sizing pipeline tests (services/sizing_pipeline) — the runner-export → engine → files wiring.

Feeds synthetic per-trade records (the runner→engine contract) through the pipeline and
checks the engine result plus the persisted artifacts (decisions.jsonl, timeline, daily_pnl).
"""

import json

from services.sizing_engine import MODE_BULLET, MODE_CONSISTENT, EngineResult, SizedTrade
from services.sizing_pipeline import (
    engine_result_to_kpis,
    is_micro_instrument,
    run_sizing_engine,
    size_run_for_rulesets,
)


def _ruleset():
    return {
        "id": "lucidflex_50k_eval",
        "ruleset_type": "prop_eval",
        "account_size": 50000,
        "profit_target": 3000,
        "max_loss_eod": 2000,
        "mll_lock_balance": 50100,
        "consistency_pct": None,
        "daily_loss_cap": None,
        "risk_per_trade_pct": None,
        "daily_halt_fraction": None,
        "daily_profit_target": None,
        "max_drawdown_from_peak_pct": None,
        "max_contracts": {"mini_max": 4, "micro_max": 40, "scaling": None},
    }


def _records():
    return [
        {
            "index": 1,
            "entry_time": "2024-01-02T09:40:00",
            "exit_time": "2024-01-02T10:00:00",
            "direction": "Long",
            "entry_price": 17000,
            "exit_price": 17010,
            "stop_distance": 5,
            "point_value": 2,
            "commission_per_side": 0,
            "exit_reason": "ORB_Long Profit target",
        },
        {
            "index": 2,
            "entry_time": "2024-01-03T09:40:00",
            "exit_time": "2024-01-03T09:55:00",
            "direction": "Short",
            "entry_price": 17000,
            "exit_price": 17005,
            "stop_distance": 5,
            "point_value": 2,
            "commission_per_side": 0,
            "exit_reason": "Stop loss",
        },
    ]


def test_micro_inference():
    assert is_micro_instrument("MNQ 06-26") is True
    assert is_micro_instrument("NQ 06-26") is False
    assert is_micro_instrument("") is False


def test_pipeline_runs_engine_and_persists(tmp_path):
    res = run_sizing_engine(
        "run42",
        _records(),
        _ruleset(),
        mode=MODE_CONSISTENT,
        instrument="MNQ 06-26",
        strategy="ORB",
        results_dir=tmp_path,
    )

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
    assert first["exit"]["reason"] == "target"  # classified from "Profit target"

    daily = json.loads((run_dir / "engine_daily_pnl.json").read_text())
    assert daily == res.daily_pnl


def test_pipeline_bullet_sizes_to_ladder(tmp_path):
    # Bullet on a micro instrument → capped by the firm's micro ladder (40).
    res = run_sizing_engine(
        "run43",
        _records()[:1],
        _ruleset(),
        mode=MODE_BULLET,
        instrument="MNQ 06-26",
        results_dir=tmp_path,
    )
    assert res.decisions[0]["sizing"]["contracts"] == 40
    assert res.decisions[0]["sizing"]["bound_by"] == "contract_ladder"


def test_size_run_for_rulesets_sizes_each_and_persists_primary_only(tmp_path):
    # Two firms with different micro ladders → bullet sizes each to its own cap.
    firm_a = {**_ruleset(), "id": "firm_a"}
    firm_a["max_contracts"] = {"mini_max": 4, "micro_max": 40, "scaling": None}
    firm_b = {**_ruleset(), "id": "firm_b"}
    firm_b["max_contracts"] = {"mini_max": 2, "micro_max": 10, "scaling": None}

    out = size_run_for_rulesets(
        "run50",
        _records()[:1],
        [firm_a, firm_b],
        mode=MODE_BULLET,
        instrument="MNQ 06-26",
        results_dir=tmp_path,
    )

    # One grade-ready entry per ruleset, each with its own sized contracts.
    assert set(out) == {"firm_a", "firm_b"}
    assert out["firm_a"]["result"].decisions[0]["sizing"]["contracts"] == 40
    assert out["firm_b"]["result"].decisions[0]["sizing"]["contracts"] == 10
    assert "net_pnl" in out["firm_a"]["kpis"] and "net_pnl" in out["firm_b"]["kpis"]

    # The PRIMARY (first) ruleset's timeline is the run headline.
    assert (tmp_path / "run50" / "engine_timeline.json").exists()
    assert (tmp_path / "run50" / "engine_daily_pnl.json").exists()

    # EVERY ruleset's sized KPIs + daily P&L + timeline are persisted for the UI (per-firm cards
    # and charts) in one map keyed by ruleset id.
    sizing = json.loads((tmp_path / "run50" / "ruleset_sizing.json").read_text())
    assert set(sizing) == {"firm_a", "firm_b"}
    assert sizing["firm_a"]["kpis"]["net_pnl"] == out["firm_a"]["kpis"]["net_pnl"]
    assert "timeline" in sizing["firm_b"] and "daily_pnl" in sizing["firm_b"]
    # Per-firm sized equity curve (drives Drawdown / Long-Short / Calmar per firm).
    ec_a = sizing["firm_a"]["equity_curve"]
    assert ec_a and ec_a[-1]["index"] == len(ec_a)
    assert set(ec_a[0]) >= {"index", "equity", "date", "direction", "profit"}
    assert ec_a[0]["direction"] in ("Long", "Short")


def _sized(index, contracts, net, skipped=False):
    return SizedTrade(
        index=index,
        day="2024-01-02",
        direction=1,
        contracts=contracts,
        net_pnl=net,
        bound_by="x",
        risk_per_contract=10.0,
        skipped=skipped,
    )


def test_kpis_from_engine_result_derives_summary():
    # Two wins (+300, +100), one loss (-200), one skipped (must not count).
    res = EngineResult(
        ruleset_id="r",
        net_pnl=200.0,
        sized_trades=[
            _sized(1, 2, 300.0),
            _sized(2, 1, -200.0),
            _sized(3, 1, 100.0),
            _sized(4, 0, 0.0, skipped=True),
        ],
    )
    k = engine_result_to_kpis(res)
    assert k["trade_count"] == 3  # skipped excluded
    assert k["net_pnl"] == 200.0
    assert k["profit_factor"] == 2.0  # 400 gross win / 200 gross loss
    assert k["win_rate"] == 0.6667  # 2 of 3, a fraction like every other path
    assert k["avg_win"] == 200.0 and k["avg_loss"] == -200.0


def test_kpis_max_drawdown_is_peak_to_trough():
    # Equity walk by index: +500 (peak 500) → -300 (trough 200) → +100 (300). Max DD = 300.
    res = EngineResult(
        ruleset_id="r",
        net_pnl=300.0,
        sized_trades=[
            _sized(1, 1, 500.0),
            _sized(2, 1, -300.0),
            _sized(3, 1, 100.0),
        ],
    )
    assert engine_result_to_kpis(res)["max_drawdown"] == 300.0


def test_kpis_no_losses_profit_factor_is_finite():
    res = EngineResult(
        ruleset_id="r",
        net_pnl=150.0,
        sized_trades=[
            _sized(1, 1, 150.0),
        ],
    )
    k = engine_result_to_kpis(res)
    assert k["profit_factor"] == 150.0  # finite stand-in, not inf
    assert "avg_loss" not in k


# ── Self-sizing strategies must NOT be re-sized ──────────────────────────────


def test_self_sizing_strategy_keeps_its_own_pnl(fresh_db, monkeypatch, tmp_path):
    """A self-sizing strategy already applied its own risk % to every trade. If the engine
    re-sizes it, the KPI cards (engine-sized) disagree with the equity chart (strategy-sized)
    on the same page, and the strategy's real risk % is silently discarded.

    Drives the real completion path, so the guard can't be bypassed by a caller.
    """
    import asyncio
    import time

    from services import backtest_runner, lab_db

    lab_db.upsert_strategy(
        {
            "id": "selfsizer",
            "name": "Self",
            "class_name": "SelfStrategy",
            "source_path": "strategies/python/selfsizer",
            "scanned_at": int(time.time()),
            "runner": "python",
            "self_sizing": True,
        }
    )
    lab_db.insert_run(
        {
            "run_id": "r1",
            "strategy_id": "selfsizer",
            "instrument": "XAUUSD.s",
            "params": {},
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2026-01-01",
            "end_date": "2026-02-01",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "status": "running",
            "created_at": int(time.time()),
            "runner": "python",
            "evaluate_rulesets": ["unconstrained"],
        }
    )

    # The strategy's OWN numbers — engine_trades present, so the old code would have re-sized.
    STRATEGY_NET = 4242.0
    results = {
        "kpis": {"net_pnl": STRATEGY_NET, "trade_count": 1, "win_trades": 1},
        "equity_curve": [
            {
                "index": 1,
                "equity": STRATEGY_NET,
                "date": "2026-01-05",
                "direction": "Long",
                "profit": STRATEGY_NET,
            }
        ],
        "daily_pnl": [{"date": "2026-01-05", "pnl": STRATEGY_NET}],
        "engine_trades": [
            {
                "index": 1,
                "entry_time": "2026-01-05T10:00:00+00:00",
                "exit_time": "2026-01-05T12:00:00+00:00",
                "direction": 1,
                "entry_price": 2000.0,
                "exit_price": 2010.0,
                "stop_distance": 5.0,
                "point_value": 100.0,
                "commission_per_side": 0.0,
                "exit_reason": "tp",
            }
        ],
    }
    monkeypatch.setattr(backtest_runner.runner_dispatch, "job_results", lambda _j: results)
    monkeypatch.setattr(
        backtest_runner, "_tag_daily_pnl_with_regime", lambda *a, **k: results["daily_pnl"]
    )
    monkeypatch.setattr(backtest_runner, "_LAB_RESULTS_DIR", tmp_path)

    asyncio.run(
        backtest_runner._handle_complete("r1", "j1", "selfsizer", "XAUUSD.s", ["unconstrained"])
    )

    row = lab_db.get_run("r1")
    assert row["status"] == "complete", row.get("error_message")
    assert row["net_pnl"] == STRATEGY_NET, "the engine re-sized a self-sizing strategy"


def test_unit_size_strategy_is_still_sized_by_the_engine(fresh_db, monkeypatch, tmp_path):
    """The guard must not disarm sizing for the strategies that genuinely need it.

    Doubles as the end-to-end proof of manual mode: run row (sizing_mode=manual,
    manual_risk_pct=50) → _handle_complete → pipeline → engine.
    """
    import asyncio
    import time

    from services import backtest_runner, lab_db

    lab_db.upsert_strategy(
        {
            "id": "unitsizer",
            "name": "Unit",
            "class_name": "ORB",
            "source_path": "strategies/ninjatrader/ORB.cs",
            "scanned_at": int(time.time()),
            "runner": "ninjatrader",
            "self_sizing": False,
        }
    )
    lab_db.insert_run(
        {
            "run_id": "r2",
            "strategy_id": "unitsizer",
            "instrument": "MES 03-26",
            "params": {},
            "bar_type": "Minute",
            "bar_value": 5,
            "start_date": "2026-01-01",
            "end_date": "2026-02-01",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "status": "running",
            "created_at": int(time.time()),
            "runner": "ninjatrader",
            "evaluate_rulesets": ["unconstrained"],
            "sizing_mode": "manual",
            "manual_risk_pct": 50.0,
        }
    )

    UNIT_NET = 1000.0
    results = {
        "kpis": {"net_pnl": UNIT_NET, "trade_count": 1, "win_trades": 1},
        "equity_curve": [
            {
                "index": 1,
                "equity": UNIT_NET,
                "date": "2026-01-05",
                "direction": "Long",
                "profit": UNIT_NET,
            }
        ],
        "daily_pnl": [{"date": "2026-01-05", "pnl": UNIT_NET}],
        "engine_trades": [
            {
                "index": 1,
                "entry_time": "2026-01-05T10:00:00+00:00",
                "exit_time": "2026-01-05T12:00:00+00:00",
                "direction": 1,
                "entry_price": 2000.0,
                "exit_price": 2010.0,
                "stop_distance": 5.0,
                "point_value": 100.0,
                "commission_per_side": 0.0,
                "exit_reason": "tp",
            }
        ],
    }
    monkeypatch.setattr(backtest_runner.runner_dispatch, "job_results", lambda _j: results)
    monkeypatch.setattr(
        backtest_runner, "_tag_daily_pnl_with_regime", lambda *a, **k: results["daily_pnl"]
    )
    monkeypatch.setattr(backtest_runner, "_LAB_RESULTS_DIR", tmp_path)

    asyncio.run(
        backtest_runner._handle_complete("r2", "j2", "unitsizer", "MES 03-26", ["unconstrained"])
    )

    row = lab_db.get_run("r2")
    assert row["status"] == "complete", row.get("error_message")
    # Unconstrained: 50% of 10,000 = 5,000 budget; 5.0pt stop x $100 = $500/contract ⇒ 10
    # contracts. The trade made 10 points ⇒ 10 x 100 x 10 = $10,000, vs the $1,000 unit
    # reference. So the engine both RAN and used the manual % it was handed.
    assert row["net_pnl"] == UNIT_NET * 10, (
        f"expected the engine to size to 10 contracts, got net={row['net_pnl']}"
    )
