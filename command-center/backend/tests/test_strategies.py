"""
Strategy scanning — current contract.

The scanner reads from `<MONOREPO_ROOT>/strategies/**` : 1 NinjaTrader .cs (ORB; VWAP_MR
and Momentum deleted 2026-06-21) + 1 MT5 .mq5 (LondonBreakout; MeanReversion deleted
2026-06-22) + 1 Python package (mpc_aplus, declaring LAB_STRATEGY; added 2026-07-16)
= 3 strategies. NT8 and Python strategies get a suggested_instrument; MT5 does not. Param
types span int/double/bool (NT8), string (MT5), and all four off a dataclass (Python).
"""

import textwrap
import pytest

EXPECTED_CLASS_NAMES = {"ORB", "LondonBreakout", "MpcAplusStrategy"}

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


# ── Cold start ─────────────────────────────────────────────────────────────────

def test_scan_adds_every_strategy(client):
    r = client.post("/strategies/scan")
    assert r.status_code == 200
    data = r.json()
    assert data["added"] == 3
    assert data["updated"] == 0


def test_scan_returns_correct_class_names(client):
    client.post("/strategies/scan")
    strategies = client.get("/strategies").json()
    assert len(strategies) == 3
    assert {s["class_name"] for s in strategies} == EXPECTED_CLASS_NAMES


def test_strategies_have_populated_param_schema(client):
    client.post("/strategies/scan")
    strategies = client.get("/strategies").json()
    for s in strategies:
        schema = s["param_schema"]
        assert isinstance(schema, list) and len(schema) > 0, \
            f"{s['class_name']} has empty param_schema"
        for p in schema:
            assert p.get("name")
            assert isinstance(p.get("type"), str) and p["type"]


def test_nt8_strategies_have_suggested_instrument(client):
    """NT8 strategies get an inferred instrument; MT5 (LondonBreakout) legitimately has none."""
    client.post("/strategies/scan")
    strategies = client.get("/strategies").json()
    nt8 = [s for s in strategies if s.get("runner", "ninjatrader") == "ninjatrader"]
    assert len(nt8) == 1
    for s in nt8:
        assert s["suggested_instrument"], f"{s['class_name']} missing suggested_instrument"


# ── Idempotence ────────────────────────────────────────────────────────────────

def test_second_scan_is_idempotent(client):
    client.post("/strategies/scan")
    r = client.post("/strategies/scan")
    data = r.json()
    assert data["added"] == 0
    assert data["updated"] == 0
    assert data["skipped"] == 3


# ── Param-schema + hash update on source change ───────────────────────────────

def _write_synthetic(tmp_path, range_max):
    nt8_dir = tmp_path / "strategies" / "ninjatrader"
    nt8_dir.mkdir(parents=True, exist_ok=True)
    cs_file = nt8_dir / "SyntheticStrat.cs"
    cs_file.write_text(SYNTHETIC_CS.format(range_max=range_max))
    return cs_file


def test_range_change_updates_param_schema(fresh_db, monkeypatch, tmp_path):
    """Editing a [Range] in a .cs and rescanning updates the stored schema."""
    import config as cfg
    from services import lab_db, strategy_scanner

    cs_file = _write_synthetic(tmp_path, range_max=60)
    monkeypatch.setattr(cfg, "MONOREPO_ROOT", tmp_path)

    result1 = strategy_scanner.scan_strategies()
    assert result1["added"] == 1
    period_v1 = next(p for p in lab_db.get_strategy("syntheticstrat")["param_schema"]
                     if p["name"] == "Period")
    assert period_v1["max"] == 60

    cs_file.write_text(SYNTHETIC_CS.format(range_max=120))
    result2 = strategy_scanner.scan_strategies()
    assert result2["updated"] == 1
    assert result2["added"] == 0
    period_v2 = next(p for p in lab_db.get_strategy("syntheticstrat")["param_schema"]
                     if p["name"] == "Period")
    assert period_v2["max"] == 120


def test_source_hash_updates_on_change(fresh_db, monkeypatch, tmp_path):
    import config as cfg
    from services import lab_db, strategy_scanner

    _write_synthetic(tmp_path, range_max=60)
    monkeypatch.setattr(cfg, "MONOREPO_ROOT", tmp_path)
    strategy_scanner.scan_strategies()
    hash_v1 = lab_db.get_strategy_hash("syntheticstrat")

    _write_synthetic(tmp_path, range_max=90)
    strategy_scanner.scan_strategies()
    hash_v2 = lab_db.get_strategy_hash("syntheticstrat")
    assert hash_v1 != hash_v2
