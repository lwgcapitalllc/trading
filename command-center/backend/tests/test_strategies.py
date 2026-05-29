"""
§11 Cases 1, 2, 3 — strategy scanning.

Case 1: cold start → 3 strategies with param schemas
Case 2: scan idempotence → second scan = 0 added, 0 updated
Case 3: param schema update → changing [Range] in .cs updates stored schema

Cases 1 and 2 use the real monorepo .cs files (path from config.json).
Case 3 uses a temp .cs file to avoid touching production code.
"""

import textwrap
import time
import pytest

EXPECTED_CLASS_NAMES = {"ORB_LucidFlex", "VWAP_MR_LucidFlex", "Momentum_LucidFlex"}

SYNTHETIC_CS = textwrap.dedent("""\
    public class SyntheticStrat : Strategy
    {{
        [NinjaScriptProperty]
        [Range(5, {range_max})]
        [Display(Name = "Period", GroupName = "Strategy", Order = 1)]
        public int Period {{ get; set; }}

        protected override void OnStateChange()
        {{
            if (State == State.SetDefaults)
            {{
                Description = "Synthetic test strategy";
                Period = 20;
            }}
        }}
    }}
""")


# ── Case 1: cold start ─────────────────────────────────────────────────────────

def test_scan_adds_three_strategies(client):
    r = client.post("/strategies/scan")
    assert r.status_code == 200
    data = r.json()
    assert data["added"] == 3
    assert data["updated"] == 0


def test_scan_returns_correct_class_names(client):
    client.post("/strategies/scan")
    strategies = client.get("/strategies").json()
    assert len(strategies) == 3
    found = {s["class_name"] for s in strategies}
    assert found == EXPECTED_CLASS_NAMES


def test_strategies_have_populated_param_schema(client):
    client.post("/strategies/scan")
    strategies = client.get("/strategies").json()
    for s in strategies:
        schema = s["param_schema"]
        assert isinstance(schema, list) and len(schema) > 0, \
            f"{s['class_name']} has empty param_schema"
        for p in schema:
            assert "name" in p
            assert "type" in p
            assert p["type"] in ("int", "double", "bool")


def test_strategies_have_default_instrument(client):
    client.post("/strategies/scan")
    strategies = client.get("/strategies").json()
    for s in strategies:
        assert s["default_instrument"] is not None, \
            f"{s['class_name']} missing default_instrument"


# ── Case 2: idempotence ────────────────────────────────────────────────────────

def test_second_scan_is_idempotent(client):
    client.post("/strategies/scan")
    r = client.post("/strategies/scan")
    data = r.json()
    assert data["added"] == 0
    assert data["updated"] == 0
    assert data["skipped"] == 3


# ── Case 3: param schema update ───────────────────────────────────────────────

def test_range_change_updates_param_schema(fresh_db, monkeypatch, tmp_path):
    """
    Simulate editing a [Range] in a .cs file and rescanning.
    Uses a temp directory so production .cs files are never modified.
    """
    import config as cfg
    from services import lab_db, strategy_scanner

    # Build fake futures dir matching the scanner's expected structure
    futures_dir = tmp_path / "algos" / "markets" / "futures" / "lucid_flex"
    futures_dir.mkdir(parents=True)

    cs_file = futures_dir / "SyntheticStrat.cs"
    cs_file.write_text(SYNTHETIC_CS.format(range_max=60))

    monkeypatch.setattr(cfg, "MONOREPO_ROOT", tmp_path)

    # First scan — adds 1 strategy
    result1 = strategy_scanner.scan_strategies()
    assert result1["added"] == 1

    schema_v1 = lab_db.get_strategy("syntheticstrat")["param_schema"]
    period_v1 = next(p for p in schema_v1 if p["name"] == "Period")
    assert period_v1["max"] == 60

    # Edit the range
    cs_file.write_text(SYNTHETIC_CS.format(range_max=120))

    result2 = strategy_scanner.scan_strategies()
    assert result2["updated"] == 1
    assert result2["added"] == 0

    schema_v2 = lab_db.get_strategy("syntheticstrat")["param_schema"]
    period_v2 = next(p for p in schema_v2 if p["name"] == "Period")
    assert period_v2["max"] == 120


def test_source_hash_updates_on_change(fresh_db, monkeypatch, tmp_path):
    import config as cfg
    from services import lab_db, strategy_scanner

    futures_dir = tmp_path / "algos" / "markets" / "futures" / "lucid_flex"
    futures_dir.mkdir(parents=True)
    cs_file = futures_dir / "SyntheticStrat.cs"
    cs_file.write_text(SYNTHETIC_CS.format(range_max=60))

    monkeypatch.setattr(cfg, "MONOREPO_ROOT", tmp_path)
    strategy_scanner.scan_strategies()
    hash_v1 = lab_db.get_strategy_hash("syntheticstrat")

    cs_file.write_text(SYNTHETIC_CS.format(range_max=90))
    strategy_scanner.scan_strategies()
    hash_v2 = lab_db.get_strategy_hash("syntheticstrat")

    assert hash_v1 != hash_v2
